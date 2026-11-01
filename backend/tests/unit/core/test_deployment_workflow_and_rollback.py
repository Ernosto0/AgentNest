"""Phase 8 Session 03: deploy workflow, preflight, lock, migration gate, and rollback tests."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from app import cli
from app.core.db import migration_head, migration_revisions

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_deploy_module() -> Any:
    script_path = REPO_ROOT / "scripts" / "deploy.py"
    spec = importlib.util.spec_from_file_location("agentnest_deploy_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deploy_mod = _load_deploy_module()


def _write_prod_env(path: Path, *, separate_migrator: bool = True) -> None:
    mig_line = (
        "MIGRATION_DATABASE_URL=postgresql+psycopg://agentnest_migrator:mig_pw@postgres:5432/agentnest\n"
        if separate_migrator
        else ""
    )
    path.write_text(
        "APP_ENV=production\n"
        "SECRET_KEY=" + ("s" * 48) + "\n"
        "DATABASE_URL=postgresql+psycopg://agentnest_app:app_pw@postgres:5432/agentnest\n"
        f"{mig_line}"
        "LLM_PROVIDER=openai\n"
        "OPENAI_API_KEY=sk-test-key\n"
        "INSTAGRAM_ENABLED_PROVIDERS=mock\n"
        "ALLOW_SIMULATED_WORKSPACES=true\n"
        "MOCK_INSTAGRAM_APP_SECRET=mock-prod-secret\n"
        "MEDIA_STORAGE_BACKEND=local\n"
        "HTTP_PORT=18080\n",
        encoding="utf-8",
    )


def test_deploy_workflow_contract_enforces_tags_concurrency_ghcr_and_verified_ssh() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
    raw = workflow_path.read_text(encoding="utf-8")
    wf = yaml.safe_load(raw)

    # yaml.safe_load parses top-level 'on' as boolean True in YAML 1.1 unless quoted
    triggers = wf.get("on") or wf.get(True)
    assert triggers is not None
    assert triggers["push"]["tags"] == ["v*"]
    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    assert dispatch_inputs["environment"]["options"] == ["production", "staging"]
    assert "image_tag" in dispatch_inputs
    assert "skip_build" in dispatch_inputs

    # Least-privilege permissions and non-cancelling concurrency group per environment
    assert wf["permissions"] == {"contents": "read", "packages": "write"}
    assert wf["concurrency"] == {
        "group": "deploy-${{ inputs.environment || 'production' }}",
        "cancel-in-progress": False,
    }

    jobs = wf["jobs"]
    assert set(jobs) == {"build-and-push", "deploy"}

    # Build job publishes both backend and caddy targets and rejects mutable 'latest'
    build_steps = jobs["build-and-push"]["steps"]
    build_uses = [s.get("uses", "") for s in build_steps]
    assert any(u.startswith("docker/build-push-action@") for u in build_uses)
    assert "target: backend" in raw
    assert "target: caddy" in raw
    assert 'if [[ "${IMAGE_TAG}" == "latest" ]]' in raw

    # Deploy job enforces verified SSH known_hosts and never disables StrictHostKeyChecking
    assert "StrictHostKeyChecking=yes" in raw
    assert "StrictHostKeyChecking=no" not in raw
    assert "UserKnownHostsFile=" in raw
    assert "DEPLOY_SSH_KNOWN_HOSTS" in raw
    assert "--password-stdin" in raw
    assert "./scripts/deploy.sh" in raw


def test_compose_prod_blanks_migration_database_url_in_runtime_services() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["api"]["environment"]["MIGRATION_DATABASE_URL"] == ""
    assert services["worker"]["environment"]["MIGRATION_DATABASE_URL"] == ""
    # The one-off migrate service inherits env_file without blanking MIGRATION_DATABASE_URL
    assert services["migrate"]["environment"].get("MIGRATION_DATABASE_URL") != ""


def test_deploy_and_rollback_shell_wrappers_exist_and_delegate_to_deploy_py() -> None:
    deploy_sh = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    rollback_sh = (REPO_ROOT / "scripts" / "rollback.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in deploy_sh
    assert 'exec "${PYTHON_BIN}" "${SCRIPT_DIR}/deploy.py" deploy "$@"' in deploy_sh
    assert "set -euo pipefail" in rollback_sh
    assert 'exec "${PYTHON_BIN}" "${SCRIPT_DIR}/deploy.py" rollback "$@"' in rollback_sh


def test_cli_migration_status_head_only_and_check_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["migration-status", "--head-only"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["head_revision"] == migration_head() == "0032"
    assert out["known_revisions"] == list(migration_revisions())
    assert len(out["known_revisions"]) >= 32

    # check-config --production --require-separated-migration-credentials
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "k" * 48)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://agentnest_app:app_secret@db.internal:5432/agentnest"
    )
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL",
        "postgresql+psycopg://agentnest_migrator:mig_secret@db.internal:5432/agentnest",
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("INSTAGRAM_ENABLED_PROVIDERS", "meta")
    monkeypatch.setenv("META_APP_ID", "app-id")
    monkeypatch.setenv("META_APP_SECRET", "meta-secret")
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "verify-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEYS", "k1:" + base64.b64encode(b"x" * 32).decode("ascii"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_ACTIVE_KEY_ID", "k1")
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "prod-bucket")
    monkeypatch.setenv("S3_REGION", "eu-central-1")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "s3-access")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s3-secret")
    cli.get_settings.cache_clear()
    try:
        rc = cli.main(["check-config", "--production", "--require-separated-migration-credentials"])
        assert rc == 0
        cfg_out = json.loads(capsys.readouterr().out)
        assert cfg_out["migration_credentials_separated"] is True
        assert "app_secret" not in json.dumps(cfg_out)
        assert "mig_secret" not in json.dumps(cfg_out)

        # Same user for both URLs fails --require-separated-migration-credentials
        monkeypatch.setenv(
            "MIGRATION_DATABASE_URL",
            "postgresql+psycopg://agentnest_app:other_pw@db.internal:5432/agentnest",
        )
        cli.get_settings.cache_clear()
        rc_same = cli.main(
            ["check-config", "--production", "--require-separated-migration-credentials"]
        )
        assert rc_same == 1
        assert "distinct database role" in capsys.readouterr().err
    finally:
        cli.get_settings.cache_clear()


def test_validate_image_tag_and_env_permissions(tmp_path: Path) -> None:
    assert deploy_mod.validate_image_tag("v0.8.0") == "v0.8.0"
    assert deploy_mod.validate_image_tag("sha-641b1f5a9bc0") == "sha-641b1f5a9bc0"
    assert deploy_mod.validate_image_tag("latest", allow_latest=True) == "latest"

    with pytest.raises(deploy_mod.DeploymentError, match="mutable 'latest'"):
        deploy_mod.validate_image_tag("latest", allow_latest=False)
    with pytest.raises(deploy_mod.DeploymentError, match="must not be empty"):
        deploy_mod.validate_image_tag("   ")
    with pytest.raises(deploy_mod.DeploymentError, match="invalid characters"):
        deploy_mod.validate_image_tag("v0.8.0; rm -rf /")

    env_file = tmp_path / ".env"
    assert deploy_mod.check_env_file_permissions(env_file, enforce_posix=True) == [
        f"Environment file {str(env_file)!r} does not exist."
    ]
    env_file.write_text("APP_ENV=production\n", encoding="utf-8")
    assert deploy_mod.check_env_file_permissions(env_file, mode_override=0o600) == []
    assert deploy_mod.check_env_file_permissions(env_file, mode_override=0o400) == []
    insecure = deploy_mod.check_env_file_permissions(env_file, mode_override=0o644)
    assert len(insecure) == 1 and "0644" in insecure[0] and "chmod 600" in insecure[0]


def test_deployment_lock_prevents_overlapping_executions(tmp_path: Path) -> None:
    lock_file = tmp_path / ".deploy.lock"
    with deploy_mod.acquire_deployment_lock(lock_file):
        assert lock_file.exists()
        with (
            pytest.raises(deploy_mod.DeploymentLockError) as exc_info,
            deploy_mod.acquire_deployment_lock(lock_file),
        ):
            pass
        assert exc_info.value.exit_code == deploy_mod.EXIT_LOCKED

    # After exiting the context manager, the lock can be acquired again cleanly
    with deploy_mod.acquire_deployment_lock(lock_file):
        pass


def test_orchestrator_deploy_migration_gate_readiness_and_rollback(tmp_path: Path) -> None:
    compose_file = tmp_path / "compose.prod.yml"
    compose_file.write_text("name: test\nservices: {}\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    _write_prod_env(env_file, separate_migrator=True)
    state_file = tmp_path / ".deploy-state"
    lock_file = tmp_path / ".deploy.lock"

    recorded_cmds: list[list[str]] = []
    db_revision = "0029"
    image_heads = {"v0.8.0": "0030", "v0.8.1": "0030", "v0.9.0": "0031"}
    known_by_tag = {
        "v0.8.0": ["0029", "0030"],
        "v0.8.1": ["0029", "0030"],
        "v0.9.0": ["0029", "0030", "0031"],
    }
    should_fail_migration = False
    should_fail_readyz = False

    def fake_runner(
        args: list[str], *, env: dict[str, str] | None = None, timeout: float = 300.0
    ) -> Any:
        nonlocal db_revision
        recorded_cmds.append(list(args))
        tag = (env or {}).get("IMAGE_TAG", "v0.8.0")
        if "migration-status" in args:
            payload = {
                "current_revision": db_revision,
                "database": True,
                "head_revision": image_heads[tag],
                "known_revisions": known_by_tag[tag],
                "migrations": db_revision == image_heads[tag],
                "ready": db_revision == image_heads[tag],
            }
            return deploy_mod.CommandResult(0, json.dumps(payload), "")
        if args[-2:] == ["run", "--rm"] or (
            "run" in args and "migrate" in args and "app.cli" not in args
        ):
            if should_fail_migration:
                return deploy_mod.CommandResult(
                    1, "", "alembic error: column failed on postgresql://u:secret_pw@postgres/db"
                )
            db_revision = image_heads[tag]
            return deploy_mod.CommandResult(0, f"Upgraded to {db_revision}", "")
        if "ps" in args and "--services" in args:
            return deploy_mod.CommandResult(0, "api\nworker\ncaddy\npostgres\n", "")
        if "ps" in args:
            return deploy_mod.CommandResult(0, "NAME STATUS\napi Up\nworker Up\ncaddy Up\n", "")
        if "logs" in args:
            return deploy_mod.CommandResult(0, "api-1 | SECRET_KEY=topsecret123 startup check", "")
        return deploy_mod.CommandResult(0, "ok", "")

    def fake_fetcher(url: str, timeout: float) -> Any:
        if should_fail_readyz:
            return deploy_mod.HttpResponse(
                503,
                json.dumps(
                    {"status": "degraded", "checks": {"database": False, "migrations": False}}
                ),
            )
        return deploy_mod.HttpResponse(
            200,
            json.dumps({"status": "ok", "checks": {"database": True, "migrations": True}}),
        )

    orch = deploy_mod.DeploymentOrchestrator(
        compose_file=compose_file,
        env_file=env_file,
        project_name="agentnest",
        state_file=state_file,
        lock_file=lock_file,
        runner=fake_runner,
        fetcher=fake_fetcher,
        sleep_fn=lambda _: None,
    )

    # 1. Normal deploy of v0.8.0 (upgrades DB 0029 -> 0030 before restarting services)
    state = orch.deploy(
        image_tag="v0.8.0",
        require_separated_migration_credentials=True,
        enforce_posix_perms=False,
    )
    assert state.status == "succeeded"
    assert state.active_image_tag == "v0.8.0"
    assert state.previous_db_revision == "0029"
    assert state.current_db_revision == "0030"
    # Verify migrate ran BEFORE up -d api worker caddy
    mig_idx = next(i for i, c in enumerate(recorded_cmds) if c[-3:] == ["run", "--rm", "migrate"])
    up_idx = next(
        i for i, c in enumerate(recorded_cmds) if "up" in c and c[-3:] == ["api", "worker", "caddy"]
    )
    assert mig_idx < up_idx

    # 2. Deploy v0.8.1 where /readyz fails -> diagnostics emitted, secrets redacted, rollback works
    recorded_cmds.clear()
    should_fail_readyz = True
    with pytest.raises(deploy_mod.DeploymentError) as readiness_exc:
        orch.deploy(
            image_tag="v0.8.1",
            readyz_timeout=0.01,
            enforce_posix_perms=False,
        )
    should_fail_readyz = False
    err_text = str(readiness_exc.value)
    assert "Readiness gate failed" in err_text
    assert "Deployment Failure Diagnostics" in err_text
    assert "topsecret123" not in err_text
    assert "[REDACTED]" in err_text
    failed_state = orch.load_state()
    assert failed_state.status == "readiness_failed"
    assert failed_state.active_image_tag == "v0.8.0"

    # Rollback to v0.8.0 succeeds because DB revision (0030) matches v0.8.0 head (0030)
    rb_state = orch.rollback(to_tag="v0.8.0", enforce_posix_perms=False)
    assert rb_state.status == "rolled_back"
    assert rb_state.active_image_tag == "v0.8.0"
    assert rb_state.current_db_revision == "0030"

    # 3. Failed migration halts before service rollout
    recorded_cmds.clear()
    should_fail_migration = True
    with pytest.raises(deploy_mod.DeploymentError) as mig_exc:
        orch.deploy(image_tag="v0.8.1", enforce_posix_perms=False)
    assert "Database migration failed before service rollout" in str(mig_exc.value)
    assert "secret_pw" not in str(mig_exc.value)
    assert not any("up" in c and c[-3:] == ["api", "worker", "caddy"] for c in recorded_cmds)
    assert orch.load_state().status == "migration_failed"
    should_fail_migration = False

    # 4. Deploy v0.9.0 (advances DB to 0031), then attempt image-only rollback to v0.8.0 (head 0030)
    orch.deploy(image_tag="v0.9.0", enforce_posix_perms=False)
    assert orch.load_state().current_db_revision == "0031"
    assert orch.load_state().previous_image_tag == "v0.8.0"

    recorded_cmds.clear()
    with pytest.raises(deploy_mod.RollbackIncompatibleError) as rb_exc:
        orch.rollback(enforce_posix_perms=False)
    assert rb_exc.value.exit_code == deploy_mod.EXIT_ROLLBACK_INCOMPATIBLE
    assert "0031" in str(rb_exc.value) and "0030" in str(rb_exc.value)
    assert "Restore the database from backup" in str(rb_exc.value)
    # Image-only rollback must NOT restart api/worker/caddy when schema is incompatible
    assert not any("up" in c and c[-3:] == ["api", "worker", "caddy"] for c in recorded_cmds)
