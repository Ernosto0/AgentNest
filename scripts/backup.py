#!/usr/bin/env python3
"""Nightly encrypted PostgreSQL backup orchestrator, 35-day retention pruner, and decrypt CLI.

Produces custom-format ``pg_dump -Fc`` dumps, encrypts them with authenticated AES-256-GCM
(``AGNBKP01`` envelope binding metadata as GCM AAD), uploads the encrypted archive and JSON
manifest to an off-site S3-compatible bucket and/or local backup directory, prunes archives
older than the canonical 35-day retention window after a verified upload, and writes a durable
``.backup-status.json`` heartbeat artifact for ``backend/app/operations/system_health.py``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC_HEADER = b"AGNBKP01"
PG_CUSTOM_DUMP_MAGIC = b"PGDMP"
NONCE_BYTES = 12
KEY_BYTES = 32
DEFAULT_RETENTION_DAYS = 35
DEFAULT_STATUS_FILE = ".backup-status.json"
DEFAULT_BACKUP_PREFIX = "postgres/nightly"
BACKUP_FILENAME_RE = re.compile(
    r"^(?P<backup_id>agentnest-(?P<ts>\d{8}T\d{6}Z)(?:-[A-Za-z0-9._-]+)?)\.(?P<ext>dump\.enc|manifest\.json)$"
)


class BackupError(RuntimeError):
    """Base error for backup orchestration failures."""


class BackupConfigError(BackupError):
    """Raised when backup encryption keys or target storage settings are invalid."""


class BackupTamperedError(BackupError):
    """Raised when an encrypted archive fails AES-256-GCM authentication or SHA-256 checks."""


class S3ClientProtocol(Protocol):
    """Minimal boto3 S3 client surface for off-site backup upload, verification, and pruning."""

    def put_object(self, **kwargs: Any) -> Any: ...

    def head_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def list_objects_v2(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class BackupKeyRing:
    """AES-256-GCM key ring supporting ``id:base64_key`` rotation or a single raw 32-byte key."""

    active_key_id: str
    keys: Mapping[str, bytes]

    @classmethod
    def from_raw(cls, raw_keys: str, *, active_key_id: str = "b1") -> BackupKeyRing:
        cleaned = raw_keys.strip()
        if not cleaned:
            raise BackupConfigError("BACKUP_ENCRYPTION_KEY must not be empty.")
        keys: dict[str, bytes] = {}
        first_id: str | None = None
        for entry in cleaned.split(","):
            item = entry.strip()
            if not item:
                continue
            if ":" in item:
                key_id, encoded = (part.strip() for part in item.split(":", 1))
            else:
                key_id, encoded = (active_key_id.strip() or "b1"), item
            if not key_id:
                raise BackupConfigError("BACKUP_ENCRYPTION_KEY entry has an empty key id.")
            if key_id in keys:
                raise BackupConfigError(f"Duplicate backup encryption key id: {key_id!r}")
            padded = encoded + "=" * (-len(encoded) % 4)
            try:
                raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            except ValueError as exc:
                raise BackupConfigError(
                    f"Backup encryption key {key_id!r} is not valid URL-safe base64."
                ) from exc
            if len(raw) != KEY_BYTES:
                raise BackupConfigError(
                    f"Backup encryption key {key_id!r} must decode to {KEY_BYTES} bytes "
                    f"(got {len(raw)})."
                )
            keys[key_id] = raw
            if first_id is None:
                first_id = key_id

        if not keys:
            raise BackupConfigError("BACKUP_ENCRYPTION_KEY must contain at least one key.")
        resolved_active = (
            active_key_id.strip() if active_key_id.strip() in keys else (first_id or "b1")
        )
        if resolved_active not in keys:
            raise BackupConfigError(
                f"Active backup key id {active_key_id!r} is not present in BACKUP_ENCRYPTION_KEY."
            )
        return cls(active_key_id=resolved_active, keys=keys)

    @property
    def active_key(self) -> bytes:
        return self.keys[self.active_key_id]


@dataclass(frozen=True)
class EncryptedEnvelopeHeader:
    """Authenticated header embedded at the start of every ``.dump.enc`` archive."""

    format_version: int
    algorithm: str
    key_id: str
    nonce_b64: str
    backup_id: str
    created_at: str
    alembic_revision: str
    plaintext_sha256: str
    plaintext_size_bytes: int

    def to_canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class BackupManifest:
    """Sidecar JSON metadata manifest stored alongside each encrypted backup archive."""

    backup_id: str
    created_at: str
    alembic_revision: str
    encryption_algorithm: str
    encryption_key_id: str
    plaintext_sha256: str
    plaintext_size_bytes: int
    ciphertext_sha256: str
    ciphertext_size_bytes: int
    archive_filename: str
    manifest_filename: str
    retention_days: int
    expires_at: str
    storage_targets: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BackupManifest:
        return cls(
            backup_id=str(payload["backup_id"]),
            created_at=str(payload["created_at"]),
            alembic_revision=str(payload["alembic_revision"]),
            encryption_algorithm=str(payload.get("encryption_algorithm", "AES-256-GCM")),
            encryption_key_id=str(payload["encryption_key_id"]),
            plaintext_sha256=str(payload["plaintext_sha256"]),
            plaintext_size_bytes=int(payload["plaintext_size_bytes"]),
            ciphertext_sha256=str(payload["ciphertext_sha256"]),
            ciphertext_size_bytes=int(payload["ciphertext_size_bytes"]),
            archive_filename=str(payload["archive_filename"]),
            manifest_filename=str(payload["manifest_filename"]),
            retention_days=int(payload.get("retention_days", DEFAULT_RETENTION_DAYS)),
            expires_at=str(payload["expires_at"]),
            storage_targets=[str(item) for item in payload.get("storage_targets", [])],
        )


@dataclass(frozen=True)
class BackupRunReport:
    """Summary emitted by ``backup.py run`` and persisted to ``.backup-status.json``."""

    backup_id: str
    created_at: str
    alembic_revision: str
    archive_filename: str
    manifest_filename: str
    plaintext_sha256: str
    plaintext_size_bytes: int
    ciphertext_sha256: str
    ciphertext_size_bytes: int
    encryption_key_id: str
    retention_days: int
    storage_targets: list[str]
    pruned_archives: list[str]
    status_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def format_utc_timestamp(dt: datetime) -> str:
    utc_dt = dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def parse_backup_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}T\d{6}Z", text):
        return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_libpq_url(database_url: str) -> str:
    """Convert SQLAlchemy ``postgresql+psycopg://`` URLs to libpq ``postgresql://`` URLs."""
    cleaned = database_url.strip()
    if cleaned.startswith("postgresql+psycopg://"):
        return "postgresql://" + cleaned.removeprefix("postgresql+psycopg://")
    if cleaned.startswith("postgres://"):
        return "postgresql://" + cleaned.removeprefix("postgres://")
    return cleaned


def encrypt_backup_bytes(
    plaintext: bytes,
    keyring: BackupKeyRing,
    *,
    backup_id: str,
    created_at: datetime,
    alembic_revision: str,
    nonce: bytes | None = None,
) -> tuple[bytes, EncryptedEnvelopeHeader]:
    """Encrypt a ``pg_dump -Fc`` payload using AES-256-GCM with authenticated metadata header."""
    if not plaintext.startswith(PG_CUSTOM_DUMP_MAGIC):
        raise BackupError(
            "Refusing to encrypt dump: payload does not start with PostgreSQL "
            "custom-format header 'PGDMP'."
        )
    actual_nonce = nonce if nonce is not None else os.urandom(NONCE_BYTES)
    if len(actual_nonce) != NONCE_BYTES:
        raise BackupError(f"AES-GCM nonce must be {NONCE_BYTES} bytes.")

    header = EncryptedEnvelopeHeader(
        format_version=1,
        algorithm="AES-256-GCM",
        key_id=keyring.active_key_id,
        nonce_b64=base64.urlsafe_b64encode(actual_nonce).decode("ascii"),
        backup_id=backup_id,
        created_at=created_at.astimezone(UTC).isoformat(),
        alembic_revision=alembic_revision,
        plaintext_sha256=sha256_bytes(plaintext),
        plaintext_size_bytes=len(plaintext),
    )
    header_bytes = header.to_canonical_bytes()
    prefix = MAGIC_HEADER + struct.pack(">I", len(header_bytes)) + header_bytes
    ciphertext = AESGCM(keyring.active_key).encrypt(actual_nonce, plaintext, prefix)
    return prefix + ciphertext, header


def inspect_encrypted_backup_header(
    encrypted_blob: bytes,
) -> tuple[EncryptedEnvelopeHeader, bytes, bytes]:
    """Parse the envelope header and return ``(header, aad_prefix, ciphertext)``."""
    min_len = len(MAGIC_HEADER) + 4 + 16
    if len(encrypted_blob) < min_len:
        raise BackupTamperedError(
            "Encrypted backup archive is truncated or smaller than minimum envelope size."
        )
    if not encrypted_blob.startswith(MAGIC_HEADER):
        raise BackupTamperedError(
            "Encrypted backup archive does not start with 'AGNBKP01' magic header."
        )
    header_len = struct.unpack(">I", encrypted_blob[len(MAGIC_HEADER) : len(MAGIC_HEADER) + 4])[0]
    header_start = len(MAGIC_HEADER) + 4
    header_end = header_start + header_len
    if header_len <= 0 or header_end + 16 > len(encrypted_blob):
        raise BackupTamperedError(
            "Encrypted backup archive has an invalid or corrupted header length."
        )
    try:
        raw_header = json.loads(encrypted_blob[header_start:header_end].decode("utf-8"))
        if not isinstance(raw_header, dict):
            raise ValueError("header is not a JSON object")
        header = EncryptedEnvelopeHeader(
            format_version=int(raw_header["format_version"]),
            algorithm=str(raw_header["algorithm"]),
            key_id=str(raw_header["key_id"]),
            nonce_b64=str(raw_header["nonce_b64"]),
            backup_id=str(raw_header["backup_id"]),
            created_at=str(raw_header["created_at"]),
            alembic_revision=str(raw_header["alembic_revision"]),
            plaintext_sha256=str(raw_header["plaintext_sha256"]),
            plaintext_size_bytes=int(raw_header["plaintext_size_bytes"]),
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise BackupTamperedError(f"Encrypted backup archive header is malformed: {exc}") from exc

    if header.format_version != 1 or header.algorithm != "AES-256-GCM":
        raise BackupTamperedError(
            f"Unsupported backup envelope version/algorithm: "
            f"v{header.format_version} {header.algorithm}"
        )
    return header, encrypted_blob[:header_end], encrypted_blob[header_end:]


def decrypt_backup_bytes(
    encrypted_blob: bytes,
    keyring: BackupKeyRing,
    *,
    expected_manifest: BackupManifest | None = None,
) -> tuple[bytes, EncryptedEnvelopeHeader]:
    """Verify and decrypt an ``AGNBKP01`` archive, raising ``BackupTamperedError`` on mismatch."""
    if expected_manifest is not None:
        actual_cipher_sha = sha256_bytes(encrypted_blob)
        if actual_cipher_sha != expected_manifest.ciphertext_sha256:
            raise BackupTamperedError(
                f"Ciphertext SHA-256 mismatch: expected {expected_manifest.ciphertext_sha256}, "
                f"got {actual_cipher_sha}."
            )
        if len(encrypted_blob) != expected_manifest.ciphertext_size_bytes:
            raise BackupTamperedError(
                f"Ciphertext byte size mismatch: expected "
                f"{expected_manifest.ciphertext_size_bytes}, got {len(encrypted_blob)}."
            )

    header, aad_prefix, ciphertext = inspect_encrypted_backup_header(encrypted_blob)
    key = keyring.keys.get(header.key_id)
    if key is None:
        raise BackupTamperedError(
            f"Backup archive was encrypted with key id {header.key_id!r}, "
            "which is not in BACKUP_ENCRYPTION_KEY."
        )
    padded_nonce = header.nonce_b64 + "=" * (-len(header.nonce_b64) % 4)
    try:
        nonce = base64.urlsafe_b64decode(padded_nonce.encode("ascii"))
    except ValueError as exc:
        raise BackupTamperedError("Backup archive header nonce is not valid base64.") from exc
    if len(nonce) != NONCE_BYTES:
        raise BackupTamperedError("Backup archive header nonce has an invalid byte length.")

    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad_prefix)
    except InvalidTag as exc:
        raise BackupTamperedError(
            "AES-256-GCM authentication tag verification failed; "
            "archive or header was tampered with."
        ) from exc

    actual_plain_sha = sha256_bytes(plaintext)
    if actual_plain_sha != header.plaintext_sha256 or len(plaintext) != header.plaintext_size_bytes:
        raise BackupTamperedError(
            "Decrypted payload SHA-256 or size does not match envelope header."
        )
    if expected_manifest is not None and (
        actual_plain_sha != expected_manifest.plaintext_sha256
        or len(plaintext) != expected_manifest.plaintext_size_bytes
    ):
        raise BackupTamperedError(
            "Decrypted payload SHA-256 or size does not match backup manifest."
        )
    if not plaintext.startswith(PG_CUSTOM_DUMP_MAGIC):
        raise BackupTamperedError(
            "Decrypted payload does not begin with PostgreSQL custom-format header 'PGDMP'."
        )
    return plaintext, header


def query_alembic_revision(database_url: str, *, postgres_container: str | None = None) -> str:
    """Query ``alembic_version.version_num`` using psycopg or ``docker exec ... psql``."""
    try:
        import psycopg

        libpq_url = normalize_libpq_url(database_url)
        with psycopg.connect(libpq_url, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]).strip()
    except Exception:
        if not postgres_container:
            raise

    if postgres_container:
        parsed = urllib.parse.urlsplit(normalize_libpq_url(database_url))
        user = urllib.parse.unquote(parsed.username or "postgres")
        password = urllib.parse.unquote(parsed.password or "")
        dbname = (parsed.path or "/agentnest").lstrip("/") or "agentnest"
        cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={password}",
            postgres_container,
            "psql",
            "-U",
            user,
            "-d",
            dbname,
            "-tAc",
            "SELECT version_num FROM alembic_version LIMIT 1",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[0].strip()

    raise BackupError("Could not determine current alembic_version from target database.")


def run_pg_dump_custom(
    database_url: str,
    *,
    pg_dump_bin: str = "pg_dump",
    postgres_container: str | None = None,
) -> bytes:
    """Run ``pg_dump -Fc --no-owner --no-privileges`` and return the custom-format dump bytes."""
    libpq_url = normalize_libpq_url(database_url)
    parsed = urllib.parse.urlsplit(libpq_url)
    user = urllib.parse.unquote(parsed.username or "postgres")
    password = urllib.parse.unquote(parsed.password or "")
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    dbname = (parsed.path or "/agentnest").lstrip("/") or "agentnest"

    resolved_bin = shutil.which(pg_dump_bin) if not postgres_container else None
    if resolved_bin:
        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password
        cmd = [
            resolved_bin,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--host",
            host,
            "--port",
            port,
            "--username",
            user,
            "--dbname",
            dbname,
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, check=False)  # noqa: S603
    elif postgres_container:
        cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={password}",
            postgres_container,
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--username",
            user,
            "--dbname",
            dbname,
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
    else:
        raise BackupError(
            f"{pg_dump_bin!r} was not found on PATH and no --postgres-container was provided."
        )

    if proc.returncode != 0:
        stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        raise BackupError(f"pg_dump failed with exit code {proc.returncode}: {stderr_text}")
    if not proc.stdout.startswith(PG_CUSTOM_DUMP_MAGIC):
        raise BackupError(
            "pg_dump output did not start with PostgreSQL custom-format magic 'PGDMP'."
        )
    return proc.stdout


def build_s3_client(
    *,
    endpoint_url: str | None,
    region_name: str,
    access_key_id: str | None,
    secret_access_key: str | None,
) -> S3ClientProtocol:
    import boto3
    from botocore.config import Config as BotoConfig

    return cast(
        S3ClientProtocol,
        boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region_name or "auto",
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        ),
    )


def upload_to_s3(
    s3_client: S3ClientProtocol,
    *,
    bucket: str,
    prefix: str,
    archive_filename: str,
    encrypted_bytes: bytes,
    manifest: BackupManifest,
) -> str:
    clean_prefix = prefix.strip("/")
    archive_key = f"{clean_prefix}/{archive_filename}" if clean_prefix else archive_filename
    manifest_key = (
        f"{clean_prefix}/{manifest.manifest_filename}"
        if clean_prefix
        else manifest.manifest_filename
    )
    manifest_bytes = manifest.to_json().encode("utf-8")

    s3_client.put_object(
        Bucket=bucket,
        Key=archive_key,
        Body=encrypted_bytes,
        ContentType="application/octet-stream",
        Metadata={
            "backup-id": manifest.backup_id,
            "alembic-revision": manifest.alembic_revision,
            "plaintext-sha256": manifest.plaintext_sha256,
            "ciphertext-sha256": manifest.ciphertext_sha256,
            "encryption-key-id": manifest.encryption_key_id,
        },
    )
    head = s3_client.head_object(Bucket=bucket, Key=archive_key)
    remote_size = int(head.get("ContentLength", -1))
    if remote_size != len(encrypted_bytes):
        raise BackupError(
            f"S3 upload verification failed for s3://{bucket}/{archive_key}: "
            f"expected {len(encrypted_bytes)} bytes, got {remote_size}."
        )

    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest_bytes,
        ContentType="application/json",
    )
    head_manifest = s3_client.head_object(Bucket=bucket, Key=manifest_key)
    if int(head_manifest.get("ContentLength", -1)) != len(manifest_bytes):
        raise BackupError(
            f"S3 manifest upload verification failed for s3://{bucket}/{manifest_key}."
        )
    return f"s3://{bucket}/{archive_key}"


def write_to_local_dir(
    output_dir: Path,
    *,
    archive_filename: str,
    encrypted_bytes: bytes,
    manifest: BackupManifest,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / archive_filename
    manifest_path = output_dir / manifest.manifest_filename

    with tempfile.NamedTemporaryFile(dir=output_dir, delete=False, suffix=".tmp") as tmp_archive:
        tmp_archive.write(encrypted_bytes)
        tmp_archive_path = Path(tmp_archive.name)
    tmp_archive_path.replace(archive_path)

    if sha256_file(archive_path) != manifest.ciphertext_sha256:
        raise BackupError(f"Local archive verification failed for {archive_path}.")

    with tempfile.NamedTemporaryFile(
        dir=output_dir, delete=False, suffix=".tmp", mode="w", encoding="utf-8", newline="\n"
    ) as tmp_manifest:
        tmp_manifest.write(manifest.to_json())
        tmp_manifest_path = Path(tmp_manifest.name)
    tmp_manifest_path.replace(manifest_path)

    return str(archive_path.resolve())


def _extract_backup_timestamp_from_name(filename: str) -> datetime | None:
    match = BACKUP_FILENAME_RE.match(filename)
    if not match:
        return None
    return parse_backup_timestamp(match.group("ts"))


def prune_local_backups(
    output_dir: Path,
    *,
    now: datetime,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    protect_backup_id: str | None = None,
) -> list[str]:
    """Delete local ``.dump.enc`` and ``.manifest.json`` files older than ``retention_days``."""
    if retention_days < 1:
        raise BackupConfigError("retention_days must be at least 1.")
    if not output_dir.exists():
        return []
    cutoff = now.astimezone(UTC) - timedelta(days=retention_days)
    pruned: list[str] = []

    for entry in sorted(output_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        match = BACKUP_FILENAME_RE.match(entry.name)
        if not match:
            continue
        backup_id = match.group("backup_id")
        if protect_backup_id and backup_id == protect_backup_id:
            continue
        created_at = _extract_backup_timestamp_from_name(entry.name)
        if created_at is None:
            continue
        if created_at < cutoff:
            entry.unlink()
            pruned.append(entry.name)
    return pruned


def prune_s3_backups(
    s3_client: S3ClientProtocol,
    *,
    bucket: str,
    prefix: str,
    now: datetime,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    protect_backup_id: str | None = None,
) -> list[str]:
    """Delete S3 backup archives and manifests older than ``retention_days``."""
    if retention_days < 1:
        raise BackupConfigError("retention_days must be at least 1.")
    cutoff = now.astimezone(UTC) - timedelta(days=retention_days)
    clean_prefix = prefix.strip("/")
    list_prefix = f"{clean_prefix}/" if clean_prefix else ""
    pruned: list[str] = []
    continuation_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": list_prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3_client.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []) or []:
            key = str(obj.get("Key", ""))
            filename = key.rsplit("/", 1)[-1]
            match = BACKUP_FILENAME_RE.match(filename)
            if not match:
                continue
            backup_id = match.group("backup_id")
            if protect_backup_id and backup_id == protect_backup_id:
                continue
            created_at = _extract_backup_timestamp_from_name(filename)
            if created_at is None:
                last_modified = obj.get("LastModified")
                if isinstance(last_modified, datetime):
                    created_at = (
                        last_modified.astimezone(UTC)
                        if last_modified.tzinfo
                        else last_modified.replace(tzinfo=UTC)
                    )
            if created_at is not None and created_at < cutoff:
                s3_client.delete_object(Bucket=bucket, Key=key)
                pruned.append(key)
        if not response.get("IsTruncated"):
            break
        continuation_token = str(response.get("NextContinuationToken", ""))
        if not continuation_token:
            break

    return sorted(pruned)


def write_backup_status_file(
    status_path: Path,
    *,
    now: datetime,
    succeeded: bool,
    report: BackupRunReport | None = None,
    error_message: str | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, Any]:
    """Write ``.backup-status.json`` atomically, preserving ``last_success_at`` on failure."""
    existing: dict[str, Any] = {}
    if status_path.exists():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}

    now_iso = now.astimezone(UTC).isoformat()
    if succeeded and report is not None:
        payload: dict[str, Any] = {
            "last_backup_at": report.created_at,
            "last_backup_status": "succeeded",
            "last_success_at": report.created_at,
            "last_backup_id": report.backup_id,
            "last_archive_key": report.storage_targets[0]
            if report.storage_targets
            else report.archive_filename,
            "last_archive_sha256": report.ciphertext_sha256,
            "last_archive_size_bytes": report.ciphertext_size_bytes,
            "last_plaintext_sha256": report.plaintext_sha256,
            "last_plaintext_size_bytes": report.plaintext_size_bytes,
            "last_alembic_revision": report.alembic_revision,
            "retention_days": report.retention_days,
            "pruned_archives": report.pruned_archives,
            "last_error": None,
        }
    else:
        payload = {
            "last_backup_at": now_iso,
            "last_backup_status": "failed",
            "last_success_at": existing.get("last_success_at"),
            "last_backup_id": existing.get("last_backup_id"),
            "last_archive_key": existing.get("last_archive_key"),
            "last_archive_sha256": existing.get("last_archive_sha256"),
            "last_archive_size_bytes": existing.get("last_archive_size_bytes"),
            "last_alembic_revision": existing.get("last_alembic_revision"),
            "retention_days": retention_days,
            "last_error": error_message or "Backup execution failed.",
        }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=status_path.parent,
        delete=False,
        suffix=".tmp",
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as tmp_file:
        tmp_file.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(status_path)
    return payload


def execute_backup_run(
    *,
    database_url: str,
    raw_encryption_key: str,
    active_key_id: str = "b1",
    output_dir: Path | None = None,
    s3_bucket: str | None = None,
    s3_prefix: str = DEFAULT_BACKUP_PREFIX,
    s3_endpoint_url: str | None = None,
    s3_region: str = "auto",
    s3_access_key_id: str | None = None,
    s3_secret_access_key: str | None = None,
    s3_client: S3ClientProtocol | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    status_file: Path = Path(DEFAULT_STATUS_FILE),
    postgres_container: str | None = None,
    pg_dump_bin: str = "pg_dump",
    alembic_revision: str | None = None,
    backup_id_suffix: str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    dump_fn: Callable[[], bytes] | None = None,
) -> BackupRunReport:
    """Execute a full backup, encryption, upload, verification, prune, and status write."""
    now = now_fn().astimezone(UTC)
    try:
        if retention_days < 1:
            raise BackupConfigError("BACKUP_RETENTION_DAYS must be at least 1.")
        keyring = BackupKeyRing.from_raw(raw_encryption_key, active_key_id=active_key_id)
        if output_dir is None and not (s3_bucket and s3_bucket.strip()):
            raise BackupConfigError(
                "At least one backup destination must be configured "
                "(--output-dir / BACKUP_LOCAL_DIR or BACKUP_S3_BUCKET)."
            )

        ts_label = format_utc_timestamp(now)
        suffix = f"-{backup_id_suffix.strip('-')}" if backup_id_suffix else ""
        backup_id = f"agentnest-{ts_label}{suffix}"
        archive_filename = f"{backup_id}.dump.enc"
        manifest_filename = f"{backup_id}.manifest.json"

        resolved_revision = alembic_revision or query_alembic_revision(
            database_url, postgres_container=postgres_container
        )
        plaintext = (
            dump_fn()
            if dump_fn is not None
            else run_pg_dump_custom(
                database_url,
                pg_dump_bin=pg_dump_bin,
                postgres_container=postgres_container,
            )
        )
        encrypted_bytes, header = encrypt_backup_bytes(
            plaintext,
            keyring,
            backup_id=backup_id,
            created_at=now,
            alembic_revision=resolved_revision,
        )
        cipher_sha = sha256_bytes(encrypted_bytes)
        expires_at = (now + timedelta(days=retention_days)).isoformat()

        storage_targets: list[str] = []
        pruned_archives: list[str] = []

        # Build preliminary manifest; storage_targets will reflect all verified destinations.
        planned_targets: list[str] = []
        if s3_bucket and s3_bucket.strip():
            clean_prefix = s3_prefix.strip("/")
            s3_key = f"{clean_prefix}/{archive_filename}" if clean_prefix else archive_filename
            planned_targets.append(f"s3://{s3_bucket.strip()}/{s3_key}")
        if output_dir is not None:
            planned_targets.append(str((output_dir / archive_filename).resolve()))

        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=header.created_at,
            alembic_revision=resolved_revision,
            encryption_algorithm=header.algorithm,
            encryption_key_id=header.key_id,
            plaintext_sha256=header.plaintext_sha256,
            plaintext_size_bytes=header.plaintext_size_bytes,
            ciphertext_sha256=cipher_sha,
            ciphertext_size_bytes=len(encrypted_bytes),
            archive_filename=archive_filename,
            manifest_filename=manifest_filename,
            retention_days=retention_days,
            expires_at=expires_at,
            storage_targets=planned_targets,
        )

        active_s3_client: S3ClientProtocol | None = None
        if s3_bucket and s3_bucket.strip():
            active_s3_client = s3_client or build_s3_client(
                endpoint_url=s3_endpoint_url,
                region_name=s3_region,
                access_key_id=s3_access_key_id,
                secret_access_key=s3_secret_access_key,
            )
            s3_target = upload_to_s3(
                active_s3_client,
                bucket=s3_bucket.strip(),
                prefix=s3_prefix,
                archive_filename=archive_filename,
                encrypted_bytes=encrypted_bytes,
                manifest=manifest,
            )
            storage_targets.append(s3_target)

        if output_dir is not None:
            local_target = write_to_local_dir(
                output_dir,
                archive_filename=archive_filename,
                encrypted_bytes=encrypted_bytes,
                manifest=manifest,
            )
            storage_targets.append(local_target)

        # Only prune expired backups after the new backup has been uploaded and verified.
        if active_s3_client is not None and s3_bucket and s3_bucket.strip():
            pruned_archives.extend(
                prune_s3_backups(
                    active_s3_client,
                    bucket=s3_bucket.strip(),
                    prefix=s3_prefix,
                    now=now,
                    retention_days=retention_days,
                    protect_backup_id=backup_id,
                )
            )
        if output_dir is not None:
            pruned_archives.extend(
                prune_local_backups(
                    output_dir,
                    now=now,
                    retention_days=retention_days,
                    protect_backup_id=backup_id,
                )
            )

        report = BackupRunReport(
            backup_id=backup_id,
            created_at=header.created_at,
            alembic_revision=resolved_revision,
            archive_filename=archive_filename,
            manifest_filename=manifest_filename,
            plaintext_sha256=header.plaintext_sha256,
            plaintext_size_bytes=header.plaintext_size_bytes,
            ciphertext_sha256=cipher_sha,
            ciphertext_size_bytes=len(encrypted_bytes),
            encryption_key_id=header.key_id,
            retention_days=retention_days,
            storage_targets=storage_targets,
            pruned_archives=pruned_archives,
            status_file=str(status_file),
        )
        write_backup_status_file(
            status_file,
            now=now,
            succeeded=True,
            report=report,
            retention_days=retention_days,
        )
        return report
    except Exception as exc:
        write_backup_status_file(
            status_file,
            now=now,
            succeeded=False,
            error_message=str(exc),
            retention_days=retention_days,
        )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/backup.py",
        description="AgentNest encrypted PostgreSQL backup, 35-day pruner, and decrypt tool.",
    )
    sub = parser.add_subparsers(dest="subcommand")

    p_run = sub.add_parser(
        "run", help="create, encrypt, upload, and prune nightly PostgreSQL backup"
    )
    p_run.add_argument(
        "--database-url",
        default=os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection URL (defaults to MIGRATION_DATABASE_URL or DATABASE_URL)",
    )
    p_run.add_argument(
        "--encryption-key",
        default=os.environ.get("BACKUP_ENCRYPTION_KEY", ""),
        help="Backup encryption key ring (defaults to BACKUP_ENCRYPTION_KEY)",
    )
    p_run.add_argument(
        "--active-key-id",
        default=os.environ.get("BACKUP_ENCRYPTION_ACTIVE_KEY_ID", "b1"),
        help="Active backup encryption key id (default: b1)",
    )
    p_run.add_argument(
        "--output-dir",
        default=os.environ.get("BACKUP_LOCAL_DIR", ""),
        help="Local directory for encrypted backup archive and manifest",
    )
    p_run.add_argument(
        "--s3-bucket",
        default=os.environ.get("BACKUP_S3_BUCKET", ""),
        help="Off-site S3 bucket name (defaults to BACKUP_S3_BUCKET)",
    )
    p_run.add_argument(
        "--s3-prefix",
        default=os.environ.get("BACKUP_S3_PREFIX", DEFAULT_BACKUP_PREFIX),
        help=f"Off-site S3 key prefix (default: {DEFAULT_BACKUP_PREFIX})",
    )
    p_run.add_argument(
        "--s3-endpoint-url",
        default=os.environ.get("BACKUP_S3_ENDPOINT_URL", ""),
        help="S3-compatible endpoint URL",
    )
    p_run.add_argument(
        "--s3-region",
        default=os.environ.get("BACKUP_S3_REGION", "auto"),
        help="S3 region (default: auto)",
    )
    p_run.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("BACKUP_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))),
        help=f"Retention window in days (default: {DEFAULT_RETENTION_DAYS})",
    )
    p_run.add_argument(
        "--status-file",
        default=os.environ.get("BACKUP_STATUS_FILE", DEFAULT_STATUS_FILE),
        help=f"Path to durable backup status heartbeat JSON (default: {DEFAULT_STATUS_FILE})",
    )
    p_run.add_argument(
        "--postgres-container",
        default=os.environ.get("POSTGRES_CONTAINER", ""),
        help="Optional Docker container name for pg_dump when pg_dump is not on host PATH",
    )
    p_run.add_argument("--pg-dump-bin", default="pg_dump", help="pg_dump executable name or path")
    p_run.add_argument("--alembic-revision", default="", help="Override detected Alembic revision")
    p_run.add_argument("--backup-id-suffix", default="", help="Optional suffix for backup_id")

    p_dec = sub.add_parser(
        "decrypt", help="verify and decrypt a .dump.enc archive into a pg_dump -Fc file"
    )
    p_dec.add_argument("--input", required=True, help="Path to encrypted .dump.enc archive")
    p_dec.add_argument("--output", required=True, help="Output path for decrypted pg_dump -Fc file")
    p_dec.add_argument(
        "--manifest", default="", help="Optional path to .manifest.json to cross-verify"
    )
    p_dec.add_argument(
        "--encryption-key",
        default=os.environ.get("BACKUP_ENCRYPTION_KEY", ""),
        help="Backup encryption key ring (defaults to BACKUP_ENCRYPTION_KEY)",
    )

    p_prune = sub.add_parser("prune", help="prune expired backups older than retention window")
    p_prune.add_argument(
        "--output-dir",
        default=os.environ.get("BACKUP_LOCAL_DIR", ""),
        help="Local directory containing backup archives",
    )
    p_prune.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("BACKUP_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))),
    )

    p_status = sub.add_parser("status", help="inspect backup heartbeat status file")
    p_status.add_argument(
        "--status-file",
        default=os.environ.get("BACKUP_STATUS_FILE", DEFAULT_STATUS_FILE),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if not args_list or args_list[0].startswith("-"):
        args_list = ["run", *args_list]
    parser = build_parser()
    args = parser.parse_args(args_list)

    try:
        if args.subcommand == "decrypt":
            keyring = BackupKeyRing.from_raw(args.encryption_key)
            encrypted_bytes = Path(args.input).read_bytes()
            manifest = (
                BackupManifest.from_dict(
                    json.loads(Path(args.manifest).read_text(encoding="utf-8"))
                )
                if args.manifest
                else None
            )
            plaintext, header = decrypt_backup_bytes(
                encrypted_bytes, keyring, expected_manifest=manifest
            )
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(plaintext)
            print(
                json.dumps(
                    {
                        "backup_id": header.backup_id,
                        "created_at": header.created_at,
                        "alembic_revision": header.alembic_revision,
                        "plaintext_sha256": header.plaintext_sha256,
                        "plaintext_size_bytes": header.plaintext_size_bytes,
                        "output": str(out_path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if args.subcommand == "prune":
            if not args.output_dir:
                raise BackupConfigError("--output-dir is required for prune.")
            pruned = prune_local_backups(
                Path(args.output_dir),
                now=datetime.now(UTC),
                retention_days=args.retention_days,
            )
            print(
                json.dumps(
                    {"pruned_archives": pruned, "retention_days": args.retention_days}, indent=2
                )
            )
            return 0

        if args.subcommand == "status":
            status_path = Path(args.status_file)
            if not status_path.exists():
                print(
                    json.dumps(
                        {
                            "last_backup_status": "missing",
                            "stale_or_failed": True,
                            "status_file": str(status_path),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            data = json.loads(status_path.read_text(encoding="utf-8"))
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0 if data.get("last_backup_status") == "succeeded" else 1

        report = execute_backup_run(
            database_url=args.database_url,
            raw_encryption_key=args.encryption_key,
            active_key_id=args.active_key_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            s3_bucket=args.s3_bucket or None,
            s3_prefix=args.s3_prefix,
            s3_endpoint_url=args.s3_endpoint_url or None,
            s3_region=args.s3_region,
            s3_access_key_id=os.environ.get("BACKUP_S3_ACCESS_KEY_ID") or None,
            s3_secret_access_key=os.environ.get("BACKUP_S3_SECRET_ACCESS_KEY") or None,
            retention_days=args.retention_days,
            status_file=Path(args.status_file),
            postgres_container=args.postgres_container or None,
            pg_dump_bin=args.pg_dump_bin,
            alembic_revision=args.alembic_revision or None,
            backup_id_suffix=args.backup_id_suffix or None,
        )
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
