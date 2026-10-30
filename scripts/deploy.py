#!/usr/bin/env python3
"""Production and staging deployment, migration gate, readiness check, and rollback orchestrator.

Supports both Linux VPS deployment (invoked via ``scripts/deploy.sh`` / ``scripts/rollback.sh``
or directly) and cross-platform local Docker Compose rehearsal on Windows/macOS/Linux.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_LOCKED = 2
EXIT_ROLLBACK_INCOMPATIBLE = 3

_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(@sha256:[a-f0-9]{64})?$")
_SENSITIVE_LOG_PATTERN = re.compile(
    r"([A-Za-z0-9_]*(?:token|secret|password|passwd|authorization|api[_-]?key|cookie|dsn|database_url)[A-Za-z0-9_]*)"
    r"(\s*[=:]\s*)(\S+)",
    re.IGNORECASE,
)
_PROCESS_LOCKS: set[Path] = set()


class DeploymentError(RuntimeError):
    """Raised when preflight, migration, rollout, readiness, or rollback fails."""

    def __init__(self, message: str, *, exit_code: int = EXIT_FAILURE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class DeploymentLockError(DeploymentError):
    """Raised when another deploy or rollback process holds the host lockfile."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=EXIT_LOCKED)


class RollbackIncompatibleError(DeploymentError):
    """Raised when an application-only rollback is blocked by DB migration incompatibility."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=EXIT_ROLLBACK_INCOMPATIBLE)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float = 300.0,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str


HttpFetcher = Callable[[str, float], HttpResponse]


@dataclass
class DeployState:
    project_name: str
    env_file: str
    active_image_tag: str | None = None
    previous_image_tag: str | None = None
    candidate_image_tag: str | None = None
    current_db_revision: str | None = None
    previous_db_revision: str | None = None
    target_head_revision: str | None = None
    status: str = "idle"
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, project_name: str, env_file: str) -> DeployState:
        return cls(
            project_name=str(data.get("project_name") or project_name),
            env_file=str(data.get("env_file") or env_file),
            active_image_tag=_opt_str(data.get("active_image_tag")),
            previous_image_tag=_opt_str(data.get("previous_image_tag")),
            candidate_image_tag=_opt_str(data.get("candidate_image_tag")),
            current_db_revision=_opt_str(data.get("current_db_revision")),
            previous_db_revision=_opt_str(data.get("previous_db_revision")),
            target_head_revision=_opt_str(data.get("target_head_revision")),
            status=str(data.get("status") or "idle"),
            updated_at=str(data.get("updated_at") or ""),
        )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def redact_sensitive_text(text: str) -> str:
    """Redact credentials, tokens, or connection passwords from diagnostic output (INV-10)."""
    redacted = _SENSITIVE_LOG_PATTERN.sub(r"\1\2[REDACTED]", text)
    return re.sub(r"(postgresql(?:\+\w+)?://[^:\s/]+:)([^@\s]+)(@)", r"\1***\3", redacted)


def validate_image_tag(image_tag: str, *, allow_latest: bool = False) -> str:
    """Validate that an image tag is explicit, safe, and immutable unless ``allow_latest``."""
    cleaned = image_tag.strip()
    if not cleaned:
        raise DeploymentError("IMAGE_TAG must not be empty.")
    if not _TAG_PATTERN.match(cleaned):
        raise DeploymentError(f"IMAGE_TAG {cleaned!r} contains invalid characters.")
    if cleaned == "latest" and not allow_latest:
        raise DeploymentError(
            "Refusing mutable 'latest' tag for deployment; supply a release tag (v*) "
            "or sha-<commit>, or pass --allow-latest for local rehearsal."
        )
    return cleaned


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` pairs from an environment file without executing shell expressions."""
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        val = raw_val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        elif " #" in val:
            val = val.split(" #", 1)[0].strip()
        if key:
            values[key] = val
    return values


def check_env_file_permissions(
    env_path: Path,
    *,
    mode_override: int | None = None,
    enforce_posix: bool | None = None,
) -> list[str]:
    """Verify ``.env`` existence and ``0600``/``0400`` file mode on POSIX hosts (INV-10)."""
    if not env_path.exists():
        return [f"Environment file {str(env_path)!r} does not exist."]
    if not env_path.is_file():
        return [f"Environment path {str(env_path)!r} is not a regular file."]
    should_check_mode = (
        mode_override is not None
        or enforce_posix is True
        or (enforce_posix is None and os.name == "posix")
    )
    if not should_check_mode:
        return []
    mode = mode_override if mode_override is not None else stat.S_IMODE(env_path.stat().st_mode)
    if (mode & 0o077) != 0 or (mode & 0o400) == 0:
        return [
            f"Environment file {str(env_path)!r} has insecure permissions 0{mode:03o}; "
            f"expected 0600 (run: chmod 600 {env_path})."
        ]
    return []


def _parse_db_user_and_host(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme.startswith("postgresql") or not parsed.hostname:
        return None, None, None
    db_name = parsed.path.lstrip("/") or None
    return parsed.username, parsed.hostname, db_name


def inspect_migration_credentials(
    env_vars: Mapping[str, str],
    *,
    require_separated: bool = False,
) -> tuple[bool, list[str], list[str]]:
    """Check runtime ``DATABASE_URL`` vs migration ``MIGRATION_DATABASE_URL`` separation."""
    problems: list[str] = []
    warnings: list[str] = []
    db_url = env_vars.get("DATABASE_URL", "").strip()
    mig_url = env_vars.get("MIGRATION_DATABASE_URL", "").strip()

    if not db_url:
        problems.append("DATABASE_URL must be set in the environment file.")
        return False, problems, warnings

    app_user, app_host, app_db = _parse_db_user_and_host(db_url)
    if app_host is None or app_db is None:
        problems.append("DATABASE_URL is not a valid PostgreSQL connection URL.")
        return False, problems, warnings

    if not mig_url:
        msg = (
            "MIGRATION_DATABASE_URL is not set; migrations will fall back to DATABASE_URL. "
            "Set MIGRATION_DATABASE_URL with a dedicated migration role (agentnest_migrator) "
            "for least-privilege runtime separation (ADR-025 §1.1)."
        )
        if require_separated:
            problems.append(msg)
        else:
            warnings.append(msg)
        return False, problems, warnings

    mig_user, mig_host, mig_db = _parse_db_user_and_host(mig_url)
    if mig_host is None or mig_db is None:
        problems.append("MIGRATION_DATABASE_URL is not a valid PostgreSQL connection URL.")
        return False, problems, warnings

    if app_user and mig_user and app_user == mig_user:
        msg = (
            f"MIGRATION_DATABASE_URL and DATABASE_URL use the same database role ({app_user!r}); "
            "use distinct roles (agentnest_migrator vs agentnest_app)."
        )
        if require_separated:
            problems.append(msg)
        else:
            warnings.append(msg)
        return False, problems, warnings

    if mig_url == db_url:
        msg = "MIGRATION_DATABASE_URL is identical to DATABASE_URL."
        if require_separated:
            problems.append(msg)
        else:
            warnings.append(msg)
        return False, problems, warnings

    return True, problems, warnings


def uses_bundled_postgres(env_vars: Mapping[str, str]) -> bool:
    """Return True if ``DATABASE_URL`` targets the Compose ``postgres`` service host."""
    db_url = env_vars.get("DATABASE_URL", "").strip()
    _, host, _ = _parse_db_user_and_host(db_url)
    return host == "postgres"


def evaluate_rollback_compatibility(
    *,
    target_image_tag: str,
    current_db_revision: str | None,
    target_head_revision: str | None,
    target_known_revisions: Sequence[str],
) -> tuple[bool, str]:
    """Verify whether rolling back the application image is safe for the current DB schema.

    Application-only image rollback is permitted ONLY when ``current_db_revision`` matches
    the target rollback image's ``head_revision``. If a forward migration was already applied,
    rolling back only the container image is blocked because ``/readyz`` requires
    ``current_revision == head_revision`` and the old image may not tolerate the newer schema.
    """
    if not target_head_revision:
        return (
            False,
            "Cannot determine Alembic head_revision for target rollback image "
            f"{target_image_tag!r}.",
        )
    if not current_db_revision:
        return (
            False,
            "Database has no applied Alembic revision (current_revision is None); "
            "run 'deploy' instead of 'rollback'.",
        )
    if current_db_revision == target_head_revision:
        return (
            True,
            f"Schema compatible: database revision {current_db_revision!r} matches "
            f"target image {target_image_tag!r} head revision.",
        )
    if target_known_revisions and current_db_revision not in set(target_known_revisions):
        return (
            False,
            f"Refusing image-only rollback to {target_image_tag!r}: database is at revision "
            f"{current_db_revision!r}, which is newer than target image head "
            f"{target_head_revision!r}. An incompatible or forward schema migration was applied. "
            "Restore the database from backup (Session 04) or deploy a forward-fix image.",
        )
    return (
        False,
        f"Refusing image-only rollback to {target_image_tag!r}: database current_revision "
        f"{current_db_revision!r} does not equal target image head_revision "
        f"{target_head_revision!r}.",
    )


@contextlib.contextmanager
def acquire_deployment_lock(lock_path: Path) -> Iterator[Path]:
    """Acquire an exclusive non-blocking host lockfile to prevent overlapping deploys/rollbacks."""
    resolved = lock_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved in _PROCESS_LOCKS:
        raise DeploymentLockError(
            f"Another deployment or rollback is already in progress (lock: {resolved})."
        )

    handle = resolved.open("a+b")
    locked_os = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\n")
            handle.flush()
        handle.seek(0)
        if sys.platform != "win32":
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DeploymentLockError(
                    f"Another deployment or rollback is already in progress (lock: {resolved})."
                ) from exc
        else:
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DeploymentLockError(
                    f"Another deployment or rollback is already in progress (lock: {resolved})."
                ) from exc
        locked_os = True
        _PROCESS_LOCKS.add(resolved)
        handle.seek(0)
        handle.truncate()
        metadata = json.dumps({"pid": os.getpid(), "acquired_at": _utc_now_iso()}) + "\n"
        handle.write(metadata.encode("utf-8"))
        handle.flush()
        yield resolved
    finally:
        _PROCESS_LOCKS.discard(resolved)
        if locked_os:
            with contextlib.suppress(OSError):
                if sys.platform != "win32":
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                else:
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        handle.close()


def default_command_runner(
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = 300.0,
) -> CommandResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(  # noqa: S603
        list(args),
        env=merged_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def default_http_fetcher(url: str, timeout: float) -> HttpResponse:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Unsupported URL scheme in {url!r}")
    req = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return HttpResponse(resp.status, resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return HttpResponse(exc.code, body)
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        return HttpResponse(0, f"connection_error: {exc}")


def poll_readyz(
    url: str,
    *,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 2.0,
    fetcher: HttpFetcher = default_http_fetcher,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[bool, int, str]:
    """Poll ``/readyz`` until HTTP 200 with ``database: true`` and ``migrations: true``."""
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    last_status = 0
    last_body = "not_polled"
    while True:
        resp = fetcher(url, min(5.0, max(timeout_seconds, 1.0)))
        last_status = resp.status
        last_body = resp.body
        if resp.status == 200:
            try:
                payload = json.loads(resp.body)
            except json.JSONDecodeError:
                payload = {}
            checks = payload.get("checks") if isinstance(payload, dict) else None
            if (
                isinstance(payload, dict)
                and payload.get("status") == "ok"
                and isinstance(checks, dict)
                and checks.get("database") is True
                and checks.get("migrations") is True
            ):
                return True, resp.status, resp.body
        if time.monotonic() >= deadline:
            return False, last_status, last_body
        sleep_fn(interval_seconds)


class DeploymentOrchestrator:
    """Executes preflight, migration gate, service rollout, readiness verification, and rollback."""

    def __init__(
        self,
        *,
        compose_file: Path,
        env_file: Path,
        project_name: str,
        state_file: Path,
        lock_file: Path,
        runner: CommandRunner = default_command_runner,
        fetcher: HttpFetcher = default_http_fetcher,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.compose_file = compose_file.resolve()
        self.env_file = env_file.resolve()
        self.project_name = project_name.strip() or "agentnest"
        self.state_file = state_file.resolve()
        self.lock_file = lock_file.resolve()
        self.runner = runner
        self.fetcher = fetcher
        self.sleep_fn = sleep_fn

    def load_state(self) -> DeployState:
        if not self.state_file.exists():
            return DeployState(project_name=self.project_name, env_file=str(self.env_file))
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DeployState(project_name=self.project_name, env_file=str(self.env_file))
        if not isinstance(raw, dict):
            return DeployState(project_name=self.project_name, env_file=str(self.env_file))
        return DeployState.from_dict(
            raw, project_name=self.project_name, env_file=str(self.env_file)
        )

    def save_state(self, state: DeployState) -> None:
        state.updated_at = _utc_now_iso()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if os.name == "posix":
            with contextlib.suppress(OSError):
                os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.state_file)

    def _compose_env(self, image_tag: str, env_vars: Mapping[str, str]) -> dict[str, str]:
        env = dict(env_vars)
        env["COMPOSE_PROJECT_NAME"] = self.project_name
        env["ENV_FILE"] = str(self.env_file)
        env["IMAGE_TAG"] = image_tag
        for passthrough in (
            "AGENTNEST_BACKEND_IMAGE",
            "AGENTNEST_CADDY_IMAGE",
            "HTTP_PORT",
            "HTTPS_PORT",
        ):
            if passthrough in os.environ and passthrough not in env:
                env[passthrough] = os.environ[passthrough]
        return env

    def _compose_cmd(self, *args: str, profile: str | None = None) -> list[str]:
        cmd = [
            "docker",
            "compose",
            "-p",
            self.project_name,
            "-f",
            str(self.compose_file),
            "--env-file",
            str(self.env_file),
        ]
        if profile:
            cmd.extend(["--profile", profile])
        cmd.extend(args)
        return cmd

    def preflight(
        self,
        *,
        image_tag: str,
        allow_latest: bool = False,
        require_separated_migration_credentials: bool = False,
        enforce_posix_perms: bool | None = None,
    ) -> dict[str, str]:
        """Run preflight checks before modifying any container or database state."""
        validated_tag = validate_image_tag(image_tag, allow_latest=allow_latest)
        if not self.compose_file.exists():
            raise DeploymentError(f"Compose file {str(self.compose_file)!r} does not exist.")

        perm_problems = check_env_file_permissions(self.env_file, enforce_posix=enforce_posix_perms)
        if perm_problems:
            raise DeploymentError("\n".join(perm_problems))

        env_vars = parse_env_file(self.env_file)
        _, cred_problems, cred_warnings = inspect_migration_credentials(
            env_vars,
            require_separated=require_separated_migration_credentials,
        )
        for warning in cred_warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if cred_problems:
            raise DeploymentError("\n".join(cred_problems))

        compose_env = self._compose_env(validated_tag, env_vars)
        cfg_res = self.runner(
            self._compose_cmd("config", "--quiet", profile="migrate"),
            env=compose_env,
            timeout=60.0,
        )
        if cfg_res.returncode != 0:
            detail = redact_sensitive_text(cfg_res.stderr or cfg_res.stdout)
            raise DeploymentError(f"docker compose config validation failed:\n{detail}")

        check_cmd = [
            "run",
            "--rm",
            "--no-deps",
            "migrate",
            "python",
            "-m",
            "app.cli",
            "check-config",
            "--production",
        ]
        if require_separated_migration_credentials:
            check_cmd.append("--require-separated-migration-credentials")
        app_cfg_res = self.runner(
            self._compose_cmd(*check_cmd, profile="ops"),
            env=compose_env,
            timeout=120.0,
        )
        if app_cfg_res.returncode != 0:
            raise DeploymentError(
                "Application production configuration check failed:\n"
                + redact_sensitive_text(app_cfg_res.stderr or app_cfg_res.stdout)
            )
        return env_vars

    def _query_migration_status(
        self,
        *,
        image_tag: str,
        env_vars: Mapping[str, str],
        head_only: bool = False,
    ) -> dict[str, Any]:
        cli_args = [
            "run",
            "--rm",
            *(["--no-deps"] if head_only else []),
            "migrate",
            "python",
            "-m",
            "app.cli",
            "migration-status",
            *(["--head-only"] if head_only else []),
        ]
        res = self.runner(
            self._compose_cmd(*cli_args, profile="ops"),
            env=self._compose_env(image_tag, env_vars),
            timeout=120.0,
        )
        if res.returncode != 0:
            raise DeploymentError(
                "Failed to query migration status:\n"
                + redact_sensitive_text(res.stderr or res.stdout)
            )
        try:
            payload = json.loads(res.stdout.strip())
        except json.JSONDecodeError as exc:
            raise DeploymentError(
                f"Invalid JSON from migration-status: {redact_sensitive_text(res.stdout)}"
            ) from exc
        if not isinstance(payload, dict):
            raise DeploymentError("Unexpected migration-status output format.")
        return payload

    def collect_diagnostics(self, *, image_tag: str, env_vars: Mapping[str, str]) -> str:
        """Collect ``docker compose ps`` and tail logs for failure reporting (redacted)."""
        compose_env = self._compose_env(image_tag, env_vars)
        ps_res = self.runner(self._compose_cmd("ps", "-a"), env=compose_env, timeout=30.0)
        logs_res = self.runner(
            self._compose_cmd("logs", "--no-color", "--tail=80", "api", "worker", "caddy"),
            env=compose_env,
            timeout=30.0,
        )
        sections = [
            "=== Deployment Failure Diagnostics ===",
            "--- docker compose ps -a ---",
            redact_sensitive_text((ps_res.stdout or ps_res.stderr).strip()),
            "--- container logs (api, worker, caddy) ---",
            redact_sensitive_text((logs_res.stdout or logs_res.stderr).strip()),
        ]
        return "\n".join(sections)

    def _verify_worker_running(self, *, image_tag: str, env_vars: Mapping[str, str]) -> bool:
        compose_env = self._compose_env(image_tag, env_vars)
        res = self.runner(
            self._compose_cmd("ps", "--status", "running", "--services"),
            env=compose_env,
            timeout=30.0,
        )
        if res.returncode != 0:
            return False
        running_services = {line.strip() for line in res.stdout.splitlines() if line.strip()}
        return {"api", "worker", "caddy"} <= running_services

    def deploy(
        self,
        *,
        image_tag: str,
        allow_latest: bool = False,
        skip_pull: bool = False,
        require_separated_migration_credentials: bool = False,
        readyz_url: str | None = None,
        readyz_timeout: float = 60.0,
        enforce_posix_perms: bool | None = None,
    ) -> DeployState:
        """Execute full deployment: lock -> preflight -> migrate -> up -> readyz gate."""
        with acquire_deployment_lock(self.lock_file):
            validated_tag = validate_image_tag(image_tag, allow_latest=allow_latest)
            if not skip_pull and self.compose_file.exists() and self.env_file.exists():
                env_preview = parse_env_file(self.env_file)
                pull_res = self.runner(
                    self._compose_cmd(
                        "pull", "migrate", "api", "worker", "caddy", profile="migrate"
                    ),
                    env=self._compose_env(validated_tag, env_preview),
                    timeout=600.0,
                )
                if pull_res.returncode != 0:
                    raise DeploymentError(
                        "Failed to pull container images:\n"
                        + redact_sensitive_text(pull_res.stderr or pull_res.stdout)
                    )

            env_vars = self.preflight(
                image_tag=validated_tag,
                allow_latest=allow_latest,
                require_separated_migration_credentials=require_separated_migration_credentials,
                enforce_posix_perms=enforce_posix_perms,
            )
            compose_env = self._compose_env(validated_tag, env_vars)

            if uses_bundled_postgres(env_vars):
                pg_res = self.runner(
                    self._compose_cmd("up", "-d", "--wait", "postgres"),
                    env=compose_env,
                    timeout=120.0,
                )
                if pg_res.returncode != 0:
                    raise DeploymentError(
                        "PostgreSQL service failed to start:\n"
                        + redact_sensitive_text(pg_res.stderr or pg_res.stdout)
                    )

            state = self.load_state()
            mig_before = self._query_migration_status(
                image_tag=validated_tag, env_vars=env_vars, head_only=False
            )
            pre_db_revision = _opt_str(mig_before.get("current_revision"))
            target_head = _opt_str(mig_before.get("head_revision"))

            if state.active_image_tag and state.active_image_tag != validated_tag:
                state.previous_image_tag = state.active_image_tag
            state.previous_db_revision = pre_db_revision
            state.current_db_revision = pre_db_revision
            state.candidate_image_tag = validated_tag
            state.target_head_revision = target_head
            state.status = "deploying"
            self.save_state(state)

            # Step 1: One-off migration gate before restarting api, worker, and caddy.
            mig_res = self.runner(
                self._compose_cmd("run", "--rm", "migrate", profile="migrate"),
                env=compose_env,
                timeout=300.0,
            )
            if mig_res.returncode != 0:
                state.status = "migration_failed"
                self.save_state(state)
                diagnostics = self.collect_diagnostics(image_tag=validated_tag, env_vars=env_vars)
                raise DeploymentError(
                    "Database migration failed before service rollout:\n"
                    f"{redact_sensitive_text(mig_res.stderr or mig_res.stdout)}\n{diagnostics}"
                )

            state.current_db_revision = target_head
            self.save_state(state)

            # Step 2: Rolling update of api, worker (35s lease drain), and caddy.
            up_res = self.runner(
                self._compose_cmd("up", "-d", "--remove-orphans", "api", "worker", "caddy"),
                env=compose_env,
                timeout=300.0,
            )
            if up_res.returncode != 0:
                state.status = "readiness_failed"
                self.save_state(state)
                diagnostics = self.collect_diagnostics(image_tag=validated_tag, env_vars=env_vars)
                raise DeploymentError(
                    "Service rollout ('docker compose up -d') failed:\n"
                    f"{redact_sensitive_text(up_res.stderr or up_res.stdout)}\n{diagnostics}"
                )

            # Step 3: Poll /readyz and verify worker/api/caddy containers are running.
            http_port = env_vars.get("HTTP_PORT") or os.environ.get("HTTP_PORT") or "80"
            effective_readyz_url = readyz_url or f"http://127.0.0.1:{http_port}/readyz"
            ready, last_status, last_body = poll_readyz(
                effective_readyz_url,
                timeout_seconds=readyz_timeout,
                fetcher=self.fetcher,
                sleep_fn=self.sleep_fn,
            )
            services_running = self._verify_worker_running(
                image_tag=validated_tag, env_vars=env_vars
            )
            if not ready or not services_running:
                state.status = "readiness_failed"
                self.save_state(state)
                diagnostics = self.collect_diagnostics(image_tag=validated_tag, env_vars=env_vars)
                raise DeploymentError(
                    f"Readiness gate failed for {effective_readyz_url!r} "
                    f"(http_status={last_status}, body={redact_sensitive_text(last_body)!r}, "
                    f"services_running={services_running}).\n{diagnostics}"
                )

            state.active_image_tag = validated_tag
            state.candidate_image_tag = None
            state.current_db_revision = target_head
            state.status = "succeeded"
            self.save_state(state)
            return state

    def rollback(
        self,
        *,
        to_tag: str | None = None,
        allow_latest: bool = False,
        skip_pull: bool = False,
        readyz_url: str | None = None,
        readyz_timeout: float = 60.0,
        enforce_posix_perms: bool | None = None,
    ) -> DeployState:
        """Roll back application containers to the previous image tag if schema-compatible."""
        with acquire_deployment_lock(self.lock_file):
            state = self.load_state()
            target_tag_raw = to_tag or state.previous_image_tag
            if not target_tag_raw:
                raise DeploymentError(
                    "No rollback image tag specified and no previous_image_tag recorded in "
                    f"{str(self.state_file)!r}; pass --to-tag <tag>."
                )
            target_tag = validate_image_tag(target_tag_raw, allow_latest=allow_latest)

            if not skip_pull and self.compose_file.exists() and self.env_file.exists():
                env_preview = parse_env_file(self.env_file)
                pull_res = self.runner(
                    self._compose_cmd(
                        "pull", "migrate", "api", "worker", "caddy", profile="migrate"
                    ),
                    env=self._compose_env(target_tag, env_preview),
                    timeout=600.0,
                )
                if pull_res.returncode != 0:
                    raise DeploymentError(
                        f"Failed to pull rollback image tag {target_tag!r}:\n"
                        + redact_sensitive_text(pull_res.stderr or pull_res.stdout)
                    )

            env_vars = self.preflight(
                image_tag=target_tag,
                allow_latest=allow_latest,
                require_separated_migration_credentials=False,
                enforce_posix_perms=enforce_posix_perms,
            )
            compose_env = self._compose_env(target_tag, env_vars)

            mig_info = self._query_migration_status(
                image_tag=target_tag, env_vars=env_vars, head_only=False
            )
            current_db_rev = _opt_str(mig_info.get("current_revision"))
            target_head_rev = _opt_str(mig_info.get("head_revision"))
            raw_known = mig_info.get("known_revisions")
            known_revs = (
                [str(r) for r in raw_known if isinstance(r, str)]
                if isinstance(raw_known, list)
                else []
            )

            compatible, reason = evaluate_rollback_compatibility(
                target_image_tag=target_tag,
                current_db_revision=current_db_rev,
                target_head_revision=target_head_rev,
                target_known_revisions=known_revs,
            )
            if not compatible:
                state.status = "rollback_failed"
                self.save_state(state)
                raise RollbackIncompatibleError(reason)

            up_res = self.runner(
                self._compose_cmd("up", "-d", "--remove-orphans", "api", "worker", "caddy"),
                env=compose_env,
                timeout=300.0,
            )
            if up_res.returncode != 0:
                state.status = "rollback_failed"
                self.save_state(state)
                diagnostics = self.collect_diagnostics(image_tag=target_tag, env_vars=env_vars)
                raise DeploymentError(
                    f"Rollback container restart failed for tag {target_tag!r}:\n"
                    f"{redact_sensitive_text(up_res.stderr or up_res.stdout)}\n{diagnostics}"
                )

            http_port = env_vars.get("HTTP_PORT") or os.environ.get("HTTP_PORT") or "80"
            effective_readyz_url = readyz_url or f"http://127.0.0.1:{http_port}/readyz"
            ready, last_status, last_body = poll_readyz(
                effective_readyz_url,
                timeout_seconds=readyz_timeout,
                fetcher=self.fetcher,
                sleep_fn=self.sleep_fn,
            )
            services_running = self._verify_worker_running(image_tag=target_tag, env_vars=env_vars)
            if not ready or not services_running:
                state.status = "rollback_failed"
                self.save_state(state)
                diagnostics = self.collect_diagnostics(image_tag=target_tag, env_vars=env_vars)
                raise DeploymentError(
                    f"Readiness gate failed after rollback to {target_tag!r} "
                    f"(http_status={last_status}, body={redact_sensitive_text(last_body)!r}, "
                    f"services_running={services_running}).\n{diagnostics}"
                )

            if state.active_image_tag and state.active_image_tag != target_tag:
                state.previous_image_tag = state.active_image_tag
            state.active_image_tag = target_tag
            state.candidate_image_tag = None
            state.current_db_revision = current_db_rev
            state.target_head_revision = target_head_rev
            state.status = "rolled_back"
            self.save_state(state)
            return state


def _default_state_file(project_name: str) -> Path:
    if project_name and project_name != "agentnest":
        return Path(f".deploy-state.{project_name}")
    return Path(".deploy-state")


def _default_lock_file(project_name: str) -> Path:
    if project_name and project_name != "agentnest":
        return Path(f".deploy.{project_name}.lock")
    return Path(".deploy.lock")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/deploy.py",
        description="AgentNest production/staging deployment and rollback orchestrator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--compose-file",
            default=os.environ.get("COMPOSE_FILE", "compose.prod.yml"),
            help="Docker Compose file path (default: compose.prod.yml)",
        )
        p.add_argument(
            "--env-file",
            default=os.environ.get("ENV_FILE", ".env"),
            help="Environment file path (default: .env)",
        )
        p.add_argument(
            "--project-name",
            default=os.environ.get("COMPOSE_PROJECT_NAME", "agentnest"),
            help="Docker Compose project name (default: agentnest)",
        )
        p.add_argument(
            "--state-file",
            default=os.environ.get("DEPLOY_STATE_FILE", ""),
            help="Deployment state file path (default: .deploy-state)",
        )
        p.add_argument(
            "--lock-file",
            default=os.environ.get("DEPLOY_LOCK_FILE", ""),
            help="Deployment lock file path (default: .deploy.lock)",
        )

    p_deploy = sub.add_parser(
        "deploy", help="run preflight, migrations, rollout, and /readyz check"
    )
    add_common_flags(p_deploy)
    p_deploy.add_argument(
        "--image-tag",
        default=os.environ.get("IMAGE_TAG", ""),
        required=not bool(os.environ.get("IMAGE_TAG")),
        help="Pinned container image tag to deploy (e.g. v0.8.0 or sha-abc1234)",
    )
    p_deploy.add_argument(
        "--allow-latest",
        action="store_true",
        help="allow 'latest' tag for local rehearsal builds",
    )
    p_deploy.add_argument(
        "--skip-pull",
        action="store_true",
        help="skip 'docker compose pull' (use locally built images)",
    )
    p_deploy.add_argument(
        "--require-separated-migration-credentials",
        action="store_true",
        help="fail preflight unless MIGRATION_DATABASE_URL uses a distinct role from DATABASE_URL",
    )
    p_deploy.add_argument(
        "--readyz-url",
        default=os.environ.get("DEPLOY_READYZ_URL", ""),
        help="Override /readyz URL to poll after rollout",
    )
    p_deploy.add_argument(
        "--readyz-timeout",
        type=float,
        default=float(os.environ.get("DEPLOY_READYZ_TIMEOUT", "60")),
        help="Seconds to poll /readyz before failing deployment (default: 60)",
    )

    p_rollback = sub.add_parser(
        "rollback",
        help="roll back application containers to previous image tag if schema-compatible",
    )
    add_common_flags(p_rollback)
    p_rollback.add_argument(
        "--to-tag",
        default=os.environ.get("ROLLBACK_IMAGE_TAG", ""),
        help="Explicit rollback image tag (defaults to previous_image_tag in .deploy-state)",
    )
    p_rollback.add_argument(
        "--allow-latest",
        action="store_true",
        help="allow 'latest' tag for local rehearsal builds",
    )
    p_rollback.add_argument(
        "--skip-pull",
        action="store_true",
        help="skip 'docker compose pull' (use locally cached images)",
    )
    p_rollback.add_argument(
        "--readyz-url",
        default=os.environ.get("DEPLOY_READYZ_URL", ""),
        help="Override /readyz URL to poll after rollback",
    )
    p_rollback.add_argument(
        "--readyz-timeout",
        type=float,
        default=float(os.environ.get("DEPLOY_READYZ_TIMEOUT", "60")),
        help="Seconds to poll /readyz before failing rollback (default: 60)",
    )

    p_preflight = sub.add_parser(
        "preflight", help="validate .env permissions and production config"
    )
    add_common_flags(p_preflight)
    p_preflight.add_argument(
        "--image-tag",
        default=os.environ.get("IMAGE_TAG", ""),
        required=not bool(os.environ.get("IMAGE_TAG")),
        help="Container image tag to validate",
    )
    p_preflight.add_argument(
        "--allow-latest",
        action="store_true",
        help="allow 'latest' tag for local rehearsal builds",
    )
    p_preflight.add_argument(
        "--require-separated-migration-credentials",
        action="store_true",
        help="fail preflight unless MIGRATION_DATABASE_URL uses a distinct role from DATABASE_URL",
    )

    p_status = sub.add_parser("status", help="print recorded deployment state as JSON")
    add_common_flags(p_status)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_name = str(args.project_name).strip() or "agentnest"
    state_file = Path(args.state_file) if args.state_file else _default_state_file(project_name)
    lock_file = Path(args.lock_file) if args.lock_file else _default_lock_file(project_name)

    orchestrator = DeploymentOrchestrator(
        compose_file=Path(args.compose_file),
        env_file=Path(args.env_file),
        project_name=project_name,
        state_file=state_file,
        lock_file=lock_file,
    )

    try:
        if args.command == "status":
            print(json.dumps(orchestrator.load_state().to_dict(), indent=2, sort_keys=True))
            return EXIT_OK
        if args.command == "preflight":
            orchestrator.preflight(
                image_tag=args.image_tag,
                allow_latest=bool(args.allow_latest),
                require_separated_migration_credentials=bool(
                    args.require_separated_migration_credentials
                ),
            )
            print(
                json.dumps(
                    {
                        "env_file": str(orchestrator.env_file),
                        "image_tag": args.image_tag,
                        "project_name": orchestrator.project_name,
                        "status": "preflight_ok",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return EXIT_OK
        if args.command == "deploy":
            state = orchestrator.deploy(
                image_tag=args.image_tag,
                allow_latest=bool(args.allow_latest),
                skip_pull=bool(args.skip_pull),
                require_separated_migration_credentials=bool(
                    args.require_separated_migration_credentials
                ),
                readyz_url=args.readyz_url or None,
                readyz_timeout=float(args.readyz_timeout),
            )
            print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
            return EXIT_OK
        if args.command == "rollback":
            state = orchestrator.rollback(
                to_tag=args.to_tag or None,
                allow_latest=bool(args.allow_latest),
                skip_pull=bool(args.skip_pull),
                readyz_url=args.readyz_url or None,
                readyz_timeout=float(args.readyz_timeout),
            )
            print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
            return EXIT_OK
    except DeploymentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
