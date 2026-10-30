"""Phase 8 Session 04: encrypted backups, 35-day retention pruning, system_health backup hooks,
database role verification, and post-restore worker fencing & tombstone reconciliation tests.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import cli
from app.agent.models import (
    AccountAgent,
    AgentDelegation,
    AgentSession,
    AgentStep,
    AgentThread,
)
from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.inbox.models import (
    Conversation,
    InboundEvent,
    Message,
    ReplyDraft,
)
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.memory.models import CustomerIdentity, CustomerMemory
from app.memory.service import digest
from app.operations.backup_restore import (
    AccountTombstone,
    ConversationTombstone,
    CustomerTombstone,
    TombstoneManifest,
    load_tombstone_manifest,
    post_restore_reconcile,
    provision_database_roles,
    verify_database_roles,
)
from app.operations.models import Operation
from app.operations.system_health import (
    BACKUP_STALE_THRESHOLD,
    backup_health,
    record_backup_audit,
)
from tests.factories import create_user, create_workspace

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_script_module(module_name: str, filename: str) -> Any:
    script_path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


backup_mod = _load_script_module("agentnest_backup_script", "backup.py")
restore_mod = _load_script_module("agentnest_restore_script", "restore.py")

KEY_B1 = "b1:" + base64.urlsafe_b64encode(b"B" * 32).decode("ascii")
KEY_B2 = "b2:" + base64.urlsafe_b64encode(b"C" * 32).decode("ascii")
FAKE_PG_DUMP_BYTES = b"PGDMP\x01\x0e\x00\x04\x08agentnest-custom-dump-payload-for-s04-testing"


class FakeS3Client:
    """In-memory S3-compatible client for testing upload, verification, and 35-day retention."""

    def __init__(self, *, fail_put: bool = False, corrupt_head_size: bool = False) -> None:
        self.fail_put = fail_put
        self.corrupt_head_size = corrupt_head_size
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_put:
            raise backup_mod.BackupError("S3 simulated network failure during PutObject")
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        body: bytes = kwargs["Body"]
        self.objects[(bucket, key)] = {
            "Body": body,
            "ContentLength": len(body),
            "Metadata": kwargs.get("Metadata", {}),
            "LastModified": datetime.now(UTC),
        }
        return {"ETag": '"fake-etag"'}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        obj = self.objects[(bucket, key)]
        length = int(obj["ContentLength"])
        if self.corrupt_head_size:
            length += 17
        return {"ContentLength": length, "Metadata": obj["Metadata"]}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        obj = self.objects[(bucket, key)]
        body_bytes: bytes = obj["Body"]

        class _Reader:
            def read(self) -> bytes:
                return body_bytes

        return {"Body": _Reader(), "ContentLength": len(body_bytes)}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        bucket = str(kwargs["Bucket"])
        prefix = str(kwargs.get("Prefix", ""))
        contents = []
        for (b_name, key), meta in sorted(self.objects.items()):
            if b_name == bucket and key.startswith(prefix):
                contents.append(
                    {
                        "Key": key,
                        "Size": meta["ContentLength"],
                        "LastModified": meta["LastModified"],
                    }
                )
        return {"Contents": contents, "IsTruncated": False}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        self.objects.pop((bucket, key), None)
        return {}


def test_backup_and_restore_scripts_and_compose_service_contracts() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.prod.yml").read_text(encoding="utf-8"))
    backup_service = compose["services"]["backup"]
    assert "backup" in backup_service["profiles"]
    assert backup_service["environment"]["BACKUP_RETENTION_DAYS"] == "${BACKUP_RETENTION_DAYS:-35}"
    assert "BACKUP_ENCRYPTION_KEY" in backup_service["environment"]

    backup_sh = (REPO_ROOT / "scripts" / "backup.sh").read_text(encoding="utf-8")
    restore_sh = (REPO_ROOT / "scripts" / "restore.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in backup_sh
    assert "backup.py" in backup_sh
    assert "set -euo pipefail" in restore_sh
    assert "restore.py" in restore_sh


def test_cli_generate_key_supports_backup_encryption_kind(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli.main(["generate-key", "--kind", "backup-encryption"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("b1:")
    keyring = backup_mod.BackupKeyRing.from_raw(out)
    assert keyring.active_key_id == "b1"
    assert len(keyring.active_key) == 32


def test_backup_encryption_roundtrip_key_rotation_and_tamper_rejection() -> None:
    keyring_v1 = backup_mod.BackupKeyRing.from_raw(KEY_B1, active_key_id="b1")
    now = datetime(2026, 10, 30, 2, 0, 0, tzinfo=UTC)

    encrypted, header = backup_mod.encrypt_backup_bytes(
        FAKE_PG_DUMP_BYTES,
        keyring_v1,
        backup_id="agentnest-20261030T020000Z",
        created_at=now,
        alembic_revision="0030",
    )
    assert encrypted.startswith(b"AGNBKP01")
    assert FAKE_PG_DUMP_BYTES not in encrypted
    assert header.key_id == "b1"
    assert header.alembic_revision == "0030"
    assert header.plaintext_size_bytes == len(FAKE_PG_DUMP_BYTES)

    # Rotated keyring (b2 active, b1 retained) still decrypts archives encrypted with b1
    keyring_rotated = backup_mod.BackupKeyRing.from_raw(f"{KEY_B2},{KEY_B1}", active_key_id="b2")
    decrypted, parsed_header = backup_mod.decrypt_backup_bytes(encrypted, keyring_rotated)
    assert decrypted == FAKE_PG_DUMP_BYTES
    assert parsed_header == header

    # Tampering with a single ciphertext byte must fail AES-GCM authentication
    tampered_cipher = bytearray(encrypted)
    tampered_cipher[-5] ^= 0xFF
    with pytest.raises(backup_mod.BackupTamperedError, match="authentication tag"):
        backup_mod.decrypt_backup_bytes(bytes(tampered_cipher), keyring_v1)

    # Tampering with the JSON header (bound as GCM AAD) must also fail authentication
    tampered_aad = encrypted.replace(b'"0030"', b'"0029"')
    assert tampered_aad != encrypted
    with pytest.raises(backup_mod.BackupTamperedError, match="authentication tag"):
        backup_mod.decrypt_backup_bytes(tampered_aad, keyring_v1)

    # Wrong key must fail authentication
    wrong_keyring = backup_mod.BackupKeyRing.from_raw(
        "b1:" + base64.urlsafe_b64encode(b"Z" * 32).decode("ascii")
    )
    with pytest.raises(backup_mod.BackupTamperedError, match="authentication tag"):
        backup_mod.decrypt_backup_bytes(encrypted, wrong_keyring)

    # Non-PGDMP input is refused before encryption
    with pytest.raises(backup_mod.BackupError, match="PGDMP"):
        backup_mod.encrypt_backup_bytes(
            b"not-a-pg-dump",
            keyring_v1,
            backup_id="agentnest-20261030T020000Z",
            created_at=now,
            alembic_revision="0030",
        )


def test_backup_35_day_retention_pruning_and_failed_upload_visibility(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    status_file = tmp_path / ".backup-status.json"
    s3 = FakeS3Client()
    now = datetime(2026, 10, 30, 2, 0, 0, tzinfo=UTC)

    # Seed expired (36 days old and 45 days old) and retained (34 days old and 10 days old) backups
    expired_36d = "agentnest-20260923T020000Z"
    expired_45d = "agentnest-20260914T020000Z"
    retained_34d = "agentnest-20260926T020000Z"
    retained_10d = "agentnest-20261020T020000Z"

    for bid in (expired_36d, expired_45d, retained_34d, retained_10d):
        for ext in ("dump.enc", "manifest.json"):
            fname = f"{bid}.{ext}"
            (backup_dir / fname).write_bytes(b"old-backup")
            s3.put_object(Bucket="agentnest-backups", Key=f"postgres/nightly/{fname}", Body=b"old")

    report = backup_mod.execute_backup_run(
        database_url="postgresql+psycopg://u:p@localhost:5432/agentnest",
        raw_encryption_key=KEY_B1,
        output_dir=backup_dir,
        s3_bucket="agentnest-backups",
        s3_prefix="postgres/nightly",
        s3_client=s3,
        retention_days=35,
        status_file=status_file,
        alembic_revision="0030",
        now_fn=lambda: now,
        dump_fn=lambda: FAKE_PG_DUMP_BYTES,
    )

    assert report.backup_id == "agentnest-20261030T020000Z"
    assert report.retention_days == 35
    # Expired (>35d) archives pruned in both S3 and local dir; <=35d archives retained
    remaining_local = {p.name for p in backup_dir.iterdir()}
    assert f"{expired_36d}.dump.enc" not in remaining_local
    assert f"{expired_45d}.dump.enc" not in remaining_local
    assert f"{retained_34d}.dump.enc" in remaining_local
    assert f"{retained_10d}.dump.enc" in remaining_local
    assert f"{report.backup_id}.dump.enc" in remaining_local

    remaining_s3_keys = {key for (_, key) in s3.objects}
    assert f"postgres/nightly/{expired_36d}.dump.enc" not in remaining_s3_keys
    assert f"postgres/nightly/{retained_34d}.dump.enc" in remaining_s3_keys
    assert f"postgres/nightly/{report.backup_id}.dump.enc" in remaining_s3_keys

    # Verify .backup-status.json and system_health.backup_health()
    health_ok = backup_health(now + timedelta(hours=2), status_file=status_file)
    assert health_ok.last_backup_status == "succeeded"
    assert health_ok.stale_or_failed is False
    assert health_ok.last_backup_id == "agentnest-20261030T020000Z"
    assert health_ok.age_seconds == 7200

    # After 26h + 1s without a newer backup, backup_health flags stale_or_failed=True (ADR-025 §4.3)
    health_stale = backup_health(
        now + BACKUP_STALE_THRESHOLD + timedelta(seconds=1),
        status_file=status_file,
    )
    assert health_stale.stale_or_failed is True

    # Now simulate a failed S3 upload on the next night: must raise BackupError, must NOT prune
    # existing backups, and must set .backup-status.json to "failed" while keeping last_success_at
    failing_s3 = FakeS3Client(fail_put=True)
    next_night = now + timedelta(days=1)
    with pytest.raises(backup_mod.BackupError, match="S3 simulated network failure"):
        backup_mod.execute_backup_run(
            database_url="postgresql+psycopg://u:p@localhost:5432/agentnest",
            raw_encryption_key=KEY_B1,
            s3_bucket="agentnest-backups",
            s3_prefix="postgres/nightly",
            s3_client=failing_s3,
            retention_days=35,
            status_file=status_file,
            alembic_revision="0030",
            now_fn=lambda: next_night,
            dump_fn=lambda: FAKE_PG_DUMP_BYTES,
        )

    health_failed = backup_health(next_night + timedelta(minutes=5), status_file=status_file)
    assert health_failed.last_backup_status == "failed"
    assert health_failed.stale_or_failed is True
    assert health_failed.last_success_at == now
    assert "S3 simulated network failure" in (health_failed.last_error or "")


def test_backup_audit_log_recording(db_session: Session) -> None:
    clock = FrozenClock(datetime(2026, 10, 30, 2, 5, 0, tzinfo=UTC))
    record_backup_audit(
        db_session,
        clock,
        succeeded=True,
        backup_id="agentnest-20261030T020000Z",
        archive_key="s3://agentnest-backups/postgres/nightly/agentnest-20261030T020000Z.dump.enc",
        archive_sha256="abc123",
        archive_size_bytes=4096,
        alembic_revision="0030",
        pruned_count=2,
    )
    record_backup_audit(
        db_session,
        clock,
        succeeded=False,
        backup_id="agentnest-20261031T020000Z",
        error_message="disk full",
    )
    rows = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.action.in_(("system.backup_succeeded", "system.backup_failed")))
            .order_by(AuditLog.occurred_at, AuditLog.created_at)
        )
    )
    assert [r.action for r in rows] == ["system.backup_succeeded", "system.backup_failed"]
    assert rows[0].metadata_["backup_id"] == "agentnest-20261030T020000Z"
    assert rows[1].metadata_["error"] == "disk full"


def test_post_restore_reconcile_fences_workers_operations_and_reapplies_tombstones(
    db_session: Session,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 10, 30, 3, 0, 0, tzinfo=UTC)
    workspace = create_workspace(db_session, name="Drill Workspace", slug="drill-ws")
    user = create_user(db_session, email="owner@drill.test")

    account = SocialAccount(
        workspace_id=workspace.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="ig-drill-acct-1",
        username="drillstudio",
        status="connected",
    )
    db_session.add(account)
    db_session.flush()

    # 1. Active account_agent and active agent_delegation -> must be paused and revoked
    agent = db_session.scalar(
        select(AccountAgent).where(
            AccountAgent.workspace_id == workspace.id,
            AccountAgent.social_account_id == account.id,
        )
    )
    assert agent is not None
    agent.controller_mode = "agent"
    agent.state = "active"
    agent.controller_epoch = 3
    agent.config_version = 2
    agent.persona_version = 1

    delegation = AgentDelegation(
        workspace_id=workspace.id,
        social_account_id=account.id,
        version=1,
        grantor_user_id=user.id,
        policy={"autonomy": "autonomous"},
        policy_hash="a" * 64,
        effective_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=1),
    )
    db_session.add(delegation)
    db_session.flush()

    # 2. Keep conversation (with an in_progress send_reply operation and sending ReplyDraft)
    kept_conv = Conversation(
        workspace_id=workspace.id,
        social_account_id=account.id,
        customer_external_id="cust-keep-1",
        customer_handle="kept",
        handling_mode="automatic",
        attention="none",
        is_simulated=True,
    )
    # 3. Erased customer conversation (erased after snapshot; listed in tombstone manifest)
    erased_conv = Conversation(
        workspace_id=workspace.id,
        social_account_id=account.id,
        customer_external_id="cust-erased-99",
        customer_handle="erased99",
        handling_mode="automatic",
        attention="needs_human",
        is_simulated=True,
    )
    db_session.add_all([kept_conv, erased_conv])
    db_session.flush()

    kept_msg = Message(
        workspace_id=workspace.id,
        conversation_id=kept_conv.id,
        social_account_id=account.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="mid-keep-1",
        text="Hello, what are your hours?",
        provider_timestamp=now - timedelta(minutes=10),
        is_simulated=True,
    )
    erased_msg = Message(
        workspace_id=workspace.id,
        conversation_id=erased_conv.id,
        social_account_id=account.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="mid-erased-2",
        text="Please delete all my personal messages.",
        provider_timestamp=now - timedelta(minutes=9),
        is_simulated=True,
    )
    db_session.add_all([kept_msg, erased_msg])
    db_session.flush()

    sending_draft = ReplyDraft(
        workspace_id=workspace.id,
        conversation_id=kept_conv.id,
        covers_through_message_id=kept_msg.id,
        source="ai",
        origin="legacy",
        text="We are open 08:00-22:00!",
        language="en",
        decision="auto",
        status="sending",
        created_by_actor_type="system",
        is_simulated=True,
    )
    db_session.add(sending_draft)
    db_session.flush()

    in_progress_op = Operation(
        workspace_id=workspace.id,
        operation_type="send_reply",
        idempotency_key=f"send_reply:{sending_draft.id}",
        subject_type="reply_draft",
        subject_id=sending_draft.id,
        social_account_id=account.id,
        provider_kind="mock",
        status="in_progress",
        attempts=1,
        started_at=now - timedelta(minutes=2),
        is_simulated=True,
    )
    db_session.add(in_progress_op)

    # Active AgentThread + AgentSession + AgentStep + queued send_reply job + running idempotent job
    thread = AgentThread(
        workspace_id=workspace.id,
        social_account_id=account.id,
        surface="dm",
        source_ref=f"dm:{kept_conv.id}",
        dm_conversation_id=kept_conv.id,
        state="running",
        handling_mode="agent",
        controller_epoch=3,
    )
    db_session.add(thread)
    db_session.flush()

    agent_session = AgentSession(
        workspace_id=workspace.id,
        thread_id=thread.id,
        initiating_event_cursor=1,
        goal_key="answer_dm:1",
        status="running",
    )
    db_session.add(agent_session)
    db_session.flush()

    agent_step = AgentStep(
        workspace_id=workspace.id,
        session_id=agent_session.id,
        sequence=1,
        status="claimed",
        claim_token=uuid.uuid4(),
        captured_cursor=1,
        captured_epoch=3,
        captured_deletion_generation=0,
    )
    outbound_job = Job(
        workspace_id=workspace.id,
        job_type="send_reply",
        payload={"operation_id": str(in_progress_op.id)},
        status="queued",
        run_at=now,
        max_attempts=3,
    )
    leased_idempotent_job = Job(
        workspace_id=workspace.id,
        job_type="process_inbound_event",
        payload={},
        status="running",
        run_at=now - timedelta(minutes=1),
        locked_by="worker-old-1",
        lease_expires_at=now + timedelta(minutes=4),
        max_attempts=3,
    )
    erased_inbound = InboundEvent(
        workspace_id=workspace.id,
        social_account_id=account.id,
        provider_kind="mock",
        dedup_key="dedup-erased-cust-99",
        event_type="message",
        status="processed",
        payload={"sender": {"id": "cust-erased-99"}, "text": "secret PII"},
        correlation_id=uuid.uuid4(),
        is_simulated=True,
        received_at=now - timedelta(hours=1),
    )
    erased_identity = CustomerIdentity(
        workspace_id=workspace.id,
        social_account_id=account.id,
        provider_subject_hash=digest("mock:dm:cust-erased-99"),
        evidence_kind="dm_participant",
        generation=0,
        revision=1,
        created_at=now - timedelta(hours=2),
    )
    db_session.add_all(
        [agent_step, outbound_job, leased_idempotent_job, erased_inbound, erased_identity]
    )
    db_session.flush()

    erased_memory = CustomerMemory(
        workspace_id=workspace.id,
        social_account_id=account.id,
        customer_identity_id=erased_identity.id,
        topic="schedule",
        kind="preference",
        body="Customer prefers morning slots",
        version=1,
        updated_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
    )
    db_session.add(erased_memory)
    db_session.flush()

    manifest_file = tmp_path / "tombstones.json"
    manifest_file.write_text(
        json.dumps(
            {
                "customers": [
                    {
                        "workspace_id": str(workspace.id),
                        "social_account_id": str(account.id),
                        "external_customer_id": "cust-erased-99",
                        "reason": "gdpr_erasure_after_snapshot",
                    }
                ],
                "conversations": [],
                "accounts": [],
                "workspaces": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    loaded_manifest = load_tombstone_manifest(manifest_file)
    assert isinstance(loaded_manifest, TombstoneManifest)
    assert len(loaded_manifest.customers) == 1
    assert isinstance(loaded_manifest.customers[0], CustomerTombstone)

    report = post_restore_reconcile(db_session, now, tombstone_manifest=loaded_manifest)

    # Verify fencing metrics
    assert report.paused_account_agents >= 1
    assert report.revoked_agent_delegations >= 1
    assert report.fenced_operations == 1
    assert report.fenced_reply_drafts == 1
    assert report.enqueued_reconcile_jobs == 1
    assert report.cancelled_agent_sessions >= 1
    assert report.abandoned_agent_steps >= 1
    assert report.cancelled_outbound_jobs >= 1
    assert report.released_running_jobs >= 1
    assert report.reapplied_customer_tombstones == 1

    # Verify DB state after fencing
    db_session.refresh(agent)
    db_session.refresh(delegation)
    db_session.refresh(in_progress_op)
    db_session.refresh(sending_draft)
    db_session.refresh(agent_session)
    db_session.refresh(agent_step)
    db_session.refresh(outbound_job)
    db_session.refresh(leased_idempotent_job)
    db_session.refresh(erased_inbound)
    db_session.refresh(erased_identity)

    assert agent.state == "paused"
    assert agent.controller_epoch == 4
    assert delegation.revoked_at == now
    assert in_progress_op.status == "outcome_unknown"
    assert in_progress_op.last_error_code == "RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN"
    assert sending_draft.status == "outcome_unknown"
    assert agent_session.status == "cancelled"
    assert agent_step.status == "abandoned"
    assert outbound_job.status == "cancelled"
    assert leased_idempotent_job.status == "queued"
    assert leased_idempotent_job.locked_by is None

    # Kept conversation is intact; erased customer conversation & memory are purged
    assert db_session.get(Conversation, kept_conv.id) is not None
    assert db_session.get(Conversation, erased_conv.id) is None
    assert erased_inbound.payload is None
    assert db_session.get(CustomerMemory, erased_memory.id) is None
    assert erased_identity.generation >= 1

    # Verify ConversationTombstone and AccountTombstone dataclasses also parse cleanly
    extra_manifest = TombstoneManifest.from_dict(
        {
            "conversations": [
                {"workspace_id": str(workspace.id), "conversation_id": str(kept_conv.id)}
            ],
            "accounts": [{"workspace_id": str(workspace.id), "social_account_id": str(account.id)}],
        }
    )
    assert isinstance(extra_manifest.conversations[0], ConversationTombstone)
    assert isinstance(extra_manifest.accounts[0], AccountTombstone)


def test_provision_and_verify_database_roles_enforces_least_privilege_and_append_only(
    db_session: Session,
) -> None:
    provision_database_roles(
        db_session,
        migrator_role="agentnest_migrator",
        app_role="agentnest_app",
        worker_role="agentnest_worker",
    )
    report = verify_database_roles(
        db_session,
        migrator_role="agentnest_migrator",
        runtime_roles=("agentnest_app", "agentnest_worker"),
    )
    assert report.verified is True
    assert report.errors == []

    # If someone grants DELETE on audit_logs to agentnest_app, verify_database_roles must fail
    db_session.execute(text('GRANT DELETE ON TABLE public."audit_logs" TO "agentnest_app"'))
    bad_report = verify_database_roles(
        db_session,
        migrator_role="agentnest_migrator",
        runtime_roles=("agentnest_app", "agentnest_worker"),
    )
    assert bad_report.verified is False
    assert any("audit_logs" in err and "DELETE" in err for err in bad_report.errors)
