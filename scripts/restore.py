#!/usr/bin/env python3
"""Encrypted PostgreSQL backup restore, role verification, and post-restore fencing orchestrator.

Restores an ``AGNBKP01`` AES-256-GCM encrypted ``pg_dump -Fc`` archive into an isolated PostgreSQL
database:
  1. Refuses to overwrite a non-empty target database unless ``--allow-overwrite-disposable``
     is set.
  2. Verifies archive/manifest SHA-256 and decrypts using ``BACKUP_ENCRYPTION_KEY``.
  3. Provisions ``agentnest_migrator`` / ``agentnest_app`` / ``agentnest_worker`` roles when
     requested and runs
     ``pg_restore --clean --if-exists --no-owner --no-privileges --role=agentnest_migrator``.
  4. Verifies restored Alembic revision against ``migration_head()``, public table count, and
     least-privilege role separation (including ``REVOKE UPDATE, DELETE`` on ``audit_logs`` and
     ``fact_versions``).
  5. Executes post-restore worker fencing and tombstone re-application (``post_restore_reconcile``)
     before any worker is allowed to start.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.backup import (  # type: ignore[import-not-found]  # noqa: E402
    BackupError,
    BackupKeyRing,
    BackupManifest,
    build_s3_client,
    decrypt_backup_bytes,
    normalize_libpq_url,
    parse_backup_timestamp,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class RestoreError(RuntimeError):
    """Raised when pre-restore safety checks, pg_restore, role checks, or fencing fail."""


@dataclass(frozen=True)
class RestoreRunReport:
    """Complete verification and timing report emitted by ``scripts/restore.py``."""

    backup_id: str
    backup_created_at: str
    restored_at: str
    backup_age_seconds: float
    restore_duration_seconds: float
    archive_size_bytes: int
    plaintext_size_bytes: int
    alembic_revision: str
    expected_alembic_revision: str
    public_table_count: int
    target_database: str
    role_verification: dict[str, Any]
    reconciliation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_identifier(name: str, label: str = "identifier") -> str:
    if not _IDENTIFIER_RE.match(name):
        raise RestoreError(f"Invalid SQL {label}: {name!r}")
    return name


def _replace_url_dbname(database_url: str, dbname: str) -> str:
    parsed = urllib.parse.urlsplit(normalize_libpq_url(database_url))
    return str(
        urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, f"/{dbname}", parsed.query, parsed.fragment)
        )
    )


def ensure_target_database(
    target_database_url: str,
    *,
    create_if_missing: bool = False,
    allow_overwrite_disposable: bool = False,
) -> tuple[str, int]:
    """Ensure target database exists (when requested) and is empty unless overwrite is allowed."""
    import psycopg

    libpq_url = normalize_libpq_url(target_database_url)
    parsed = urllib.parse.urlsplit(libpq_url)
    target_db = _validate_identifier(
        (parsed.path or "/agentnest").lstrip("/") or "agentnest",
        "database name",
    )

    if create_if_missing:
        admin_url = _replace_url_dbname(libpq_url, "postgres")
        with (
            psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as admin_conn,
            admin_conn.cursor() as cur,
        ):
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(f'CREATE DATABASE "{target_db}"')

    with psycopg.connect(libpq_url, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        row = cur.fetchone()
        existing_tables = int(row[0]) if row else 0

    if existing_tables > 0 and not allow_overwrite_disposable:
        raise RestoreError(
            f"Target database {target_db!r} is not empty ({existing_tables} tables found). "
            "Restore must target a fresh isolated database or pass --allow-overwrite-disposable."
        )
    return target_db, existing_tables


def ensure_migrator_role_exists(target_database_url: str, migrator_role: str) -> None:
    """Ensure ``migrator_role`` exists before ``pg_restore --role=<migrator_role>`` runs."""
    import psycopg

    safe_role = _validate_identifier(migrator_role, "migrator role")
    libpq_url = normalize_libpq_url(target_database_url)
    with (
        psycopg.connect(libpq_url, autocommit=True, connect_timeout=10) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (safe_role,))
        if cur.fetchone() is None:
            cur.execute(
                f'CREATE ROLE "{safe_role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'
            )
        cur.execute("SELECT current_user, current_database()")
        current_user, current_db = cur.fetchone() or ("postgres", "agentnest")
        safe_user = _validate_identifier(str(current_user), "current user")
        safe_db = _validate_identifier(str(current_db), "current database")
        if safe_user != safe_role:
            cur.execute(f'GRANT "{safe_role}" TO "{safe_user}"')
        cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{safe_db}" TO "{safe_role}"')
        cur.execute(f'GRANT ALL ON SCHEMA public TO "{safe_role}"')


def run_pg_restore_custom(
    target_database_url: str,
    plaintext_dump: bytes,
    *,
    migrator_role: str = "agentnest_migrator",
    pg_restore_bin: str = "pg_restore",
    postgres_container: str | None = None,
    clean_existing: bool = False,
) -> None:
    """Run ``pg_restore --no-owner --no-privileges --role=<migrator_role>`` with decrypted dump."""
    safe_role = _validate_identifier(migrator_role, "migrator role")
    libpq_url = normalize_libpq_url(target_database_url)
    parsed = urllib.parse.urlsplit(libpq_url)
    user = urllib.parse.unquote(parsed.username or "postgres")
    password = urllib.parse.unquote(parsed.password or "")
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    dbname = (parsed.path or "/agentnest").lstrip("/") or "agentnest"

    restore_flags = [
        "--no-owner",
        "--no-privileges",
        f"--role={safe_role}",
        "--exit-on-error",
    ]
    if clean_existing:
        restore_flags = ["--clean", "--if-exists", *restore_flags]

    resolved_bin = shutil.which(pg_restore_bin) if not postgres_container else None
    if resolved_bin:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp_dump:
            tmp_dump.write(plaintext_dump)
            tmp_dump_path = Path(tmp_dump.name)
        try:
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password
            cmd = [
                resolved_bin,
                *restore_flags,
                "--host",
                host,
                "--port",
                port,
                "--username",
                user,
                "--dbname",
                dbname,
                str(tmp_dump_path),
            ]
            proc = subprocess.run(cmd, env=env, capture_output=True, check=False)  # noqa: S603
        finally:
            tmp_dump_path.unlink(missing_ok=True)
    elif postgres_container:
        cmd = [
            "docker",
            "exec",
            "-i",
            "-e",
            f"PGPASSWORD={password}",
            postgres_container,
            "pg_restore",
            *restore_flags,
            "--username",
            user,
            "--dbname",
            dbname,
        ]
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=plaintext_dump,
            capture_output=True,
            check=False,
        )
    else:
        raise RestoreError(
            f"{pg_restore_bin!r} was not found on PATH and no --postgres-container was provided."
        )

    if proc.returncode != 0:
        stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RestoreError(f"pg_restore failed with exit code {proc.returncode}: {stderr_text}")


def _resolve_manifest_path(archive_path: Path, explicit_manifest: str | None) -> Path | None:
    if explicit_manifest:
        path = Path(explicit_manifest)
        if not path.exists():
            raise RestoreError(f"Manifest file not found: {path}")
        return path
    if archive_path.name.endswith(".dump.enc"):
        candidate = archive_path.with_name(
            archive_path.name[: -len(".dump.enc")] + ".manifest.json"
        )
        if candidate.exists():
            return candidate
    return None


def execute_restore(
    *,
    target_database_url: str,
    raw_encryption_key: str,
    archive_path: Path | None = None,
    manifest_path: Path | None = None,
    s3_bucket: str | None = None,
    s3_key: str | None = None,
    s3_endpoint_url: str | None = None,
    s3_region: str = "auto",
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
    create_target_db: bool = False,
    allow_overwrite_disposable: bool = False,
    postgres_container: str | None = None,
    pg_restore_bin: str = "pg_restore",
    migrator_role: str = "agentnest_migrator",
    runtime_roles: Sequence[str] = ("agentnest_app", "agentnest_worker"),
    provision_roles: bool = True,
    app_role_password: str | None = None,
    worker_role_password: str | None = None,
    expected_revision: str | None = None,
    tombstone_manifest_path: Path | None = None,
    skip_reconcile: bool = False,
) -> RestoreRunReport:
    """Execute end-to-end encrypted archive verification, restore, role checks, and fencing."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.core.db import migration_head
    from app.operations.backup_restore import (
        load_tombstone_manifest,
        post_restore_reconcile,
        provision_database_roles,
        verify_database_roles,
    )

    started_monotonic = time.monotonic()
    keyring = BackupKeyRing.from_raw(raw_encryption_key)

    if archive_path is not None:
        if not archive_path.exists():
            raise RestoreError(f"Backup archive not found: {archive_path}")
        encrypted_bytes = archive_path.read_bytes()
        resolved_manifest_path = _resolve_manifest_path(
            archive_path, str(manifest_path) if manifest_path else None
        )
        manifest = (
            BackupManifest.from_dict(json.loads(resolved_manifest_path.read_text(encoding="utf-8")))
            if resolved_manifest_path is not None
            else None
        )
    elif s3_bucket and s3_key:
        s3 = build_s3_client(
            endpoint_url=s3_endpoint_url,
            region_name=s3_region,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
        )
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        encrypted_bytes = obj["Body"].read()
        manifest = None
        if s3_key.endswith(".dump.enc"):
            manifest_key = s3_key[: -len(".dump.enc")] + ".manifest.json"
            try:
                m_obj = s3.get_object(Bucket=s3_bucket, Key=manifest_key)
                manifest = BackupManifest.from_dict(
                    json.loads(m_obj["Body"].read().decode("utf-8"))
                )
            except Exception:
                manifest = None
    else:
        raise RestoreError("Provide either --archive <path> or --s3-bucket and --s3-key.")

    try:
        plaintext_dump, header = decrypt_backup_bytes(
            encrypted_bytes,
            keyring,
            expected_manifest=manifest,
        )
    except BackupError as exc:
        raise RestoreError(f"Archive decryption/authentication failed: {exc}") from exc

    target_db_name, existing_table_count = ensure_target_database(
        target_database_url,
        create_if_missing=create_target_db,
        allow_overwrite_disposable=allow_overwrite_disposable,
    )
    ensure_migrator_role_exists(target_database_url, migrator_role)
    run_pg_restore_custom(
        target_database_url,
        plaintext_dump,
        migrator_role=migrator_role,
        pg_restore_bin=pg_restore_bin,
        postgres_container=postgres_container,
        clean_existing=existing_table_count > 0 and allow_overwrite_disposable,
    )

    sa_url = (
        target_database_url
        if target_database_url.startswith("postgresql+psycopg://")
        else "postgresql+psycopg://"
        + normalize_libpq_url(target_database_url).removeprefix("postgresql://")
    )
    engine = create_engine(sa_url, future=True)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    try:
        with SessionLocal() as session, session.begin():
            rev_row = session.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).first()
            restored_revision = str(rev_row[0]).strip() if rev_row and rev_row[0] else ""
            target_expected_rev = expected_revision or migration_head() or header.alembic_revision
            if restored_revision != target_expected_rev:
                raise RestoreError(
                    f"Restored database Alembic revision {restored_revision!r} does not match "
                    f"expected revision {target_expected_rev!r}."
                )

            table_count = int(
                session.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                        """
                    )
                ).scalar_one()
            )
            if table_count < 10:
                raise RestoreError(
                    f"Restored database has unexpectedly few public tables ({table_count})."
                )

            app_role = runtime_roles[0] if runtime_roles else "agentnest_app"
            worker_role = runtime_roles[1] if len(runtime_roles) > 1 else app_role
            if provision_roles:
                provision_database_roles(
                    session,
                    migrator_role=migrator_role,
                    app_role=app_role,
                    worker_role=worker_role,
                    app_password=app_role_password,
                    worker_password=worker_role_password,
                )

            role_report = verify_database_roles(
                session,
                migrator_role=migrator_role,
                runtime_roles=runtime_roles,
            )
            if not role_report.verified:
                raise RestoreError(
                    "Database role privilege verification failed after restore: "
                    + "; ".join(role_report.errors)
                )

            reconcile_dict: dict[str, Any] = {"skipped": True}
            if not skip_reconcile:
                tombstone_manifest = (
                    load_tombstone_manifest(tombstone_manifest_path)
                    if tombstone_manifest_path is not None
                    else None
                )
                reconcile_report = post_restore_reconcile(
                    session,
                    datetime.now(UTC),
                    tombstone_manifest=tombstone_manifest,
                )
                reconcile_dict = reconcile_report.to_dict()
    finally:
        engine.dispose()

    finished_at = datetime.now(UTC)
    duration_seconds = round(time.monotonic() - started_monotonic, 3)
    created_dt = parse_backup_timestamp(header.created_at) or finished_at
    backup_age_seconds = round(max(0.0, (finished_at - created_dt).total_seconds()), 3)

    return RestoreRunReport(
        backup_id=header.backup_id,
        backup_created_at=header.created_at,
        restored_at=finished_at.isoformat(),
        backup_age_seconds=backup_age_seconds,
        restore_duration_seconds=duration_seconds,
        archive_size_bytes=len(encrypted_bytes),
        plaintext_size_bytes=len(plaintext_dump),
        alembic_revision=restored_revision,
        expected_alembic_revision=target_expected_rev,
        public_table_count=table_count,
        target_database=target_db_name,
        role_verification=role_report.to_dict(),
        reconciliation=reconcile_dict,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/restore.py",
        description="Restore an encrypted AgentNest PostgreSQL backup into an isolated database.",
    )
    parser.add_argument("--archive", default="", help="Path to local .dump.enc backup archive")
    parser.add_argument("--manifest", default="", help="Optional path to .manifest.json")
    parser.add_argument("--s3-bucket", default=os.environ.get("BACKUP_S3_BUCKET", ""))
    parser.add_argument("--s3-key", default="", help="S3 object key of .dump.enc archive")
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("BACKUP_S3_ENDPOINT_URL", ""))
    parser.add_argument("--s3-region", default=os.environ.get("BACKUP_S3_REGION", "auto"))
    parser.add_argument(
        "--target-database-url",
        required=True,
        help="Target PostgreSQL URL for restore (isolated or with --allow-overwrite-disposable)",
    )
    parser.add_argument(
        "--encryption-key",
        default=os.environ.get("BACKUP_ENCRYPTION_KEY", ""),
        help="Backup encryption key ring (defaults to BACKUP_ENCRYPTION_KEY)",
    )
    parser.add_argument(
        "--create-target-db",
        action="store_true",
        help="Create the target database if it does not exist yet",
    )
    parser.add_argument(
        "--allow-overwrite-disposable",
        action="store_true",
        help="Allow restoring into a non-empty disposable DB with pg_restore --clean --if-exists",
    )
    parser.add_argument(
        "--postgres-container",
        default=os.environ.get("POSTGRES_CONTAINER", ""),
        help="Optional Docker container name for pg_restore when pg_restore is not on host PATH",
    )
    parser.add_argument("--pg-restore-bin", default="pg_restore")
    parser.add_argument("--migrator-role", default="agentnest_migrator")
    parser.add_argument("--runtime-roles", default="agentnest_app,agentnest_worker")
    parser.add_argument(
        "--no-provision-roles",
        action="store_true",
        help="Do not provision runtime roles; only verify existing role privileges",
    )
    parser.add_argument("--app-role-password", default=None)
    parser.add_argument("--worker-role-password", default=None)
    parser.add_argument("--expected-revision", default="")
    parser.add_argument(
        "--tombstone-manifest",
        default="",
        help="Optional path to JSON tombstone manifest for post-snapshot erased entities",
    )
    parser.add_argument(
        "--skip-reconcile",
        action="store_true",
        help="Skip post-restore worker fencing and tombstone reconciliation (not recommended)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime_roles = tuple(
        role.strip() for role in (args.runtime_roles or "").split(",") if role.strip()
    )
    try:
        report = execute_restore(
            target_database_url=args.target_database_url,
            raw_encryption_key=args.encryption_key,
            archive_path=Path(args.archive) if args.archive else None,
            manifest_path=Path(args.manifest) if args.manifest else None,
            s3_bucket=args.s3_bucket or None,
            s3_key=args.s3_key or None,
            s3_endpoint_url=args.s3_endpoint_url or None,
            s3_region=args.s3_region,
            s3_access_key_id=os.environ.get("BACKUP_S3_ACCESS_KEY_ID") or None,
            s3_secret_access_key=os.environ.get("BACKUP_S3_SECRET_ACCESS_KEY") or None,
            create_target_db=args.create_target_db,
            allow_overwrite_disposable=args.allow_overwrite_disposable,
            postgres_container=args.postgres_container or None,
            pg_restore_bin=args.pg_restore_bin,
            migrator_role=args.migrator_role,
            runtime_roles=runtime_roles,
            provision_roles=not args.no_provision_roles,
            app_role_password=args.app_role_password,
            worker_role_password=args.worker_role_password,
            expected_revision=args.expected_revision or None,
            tombstone_manifest_path=(
                Path(args.tombstone_manifest) if args.tombstone_manifest else None
            ),
            skip_reconcile=args.skip_reconcile,
        )
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0
    except RestoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
