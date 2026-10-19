"""P4-03: webhook ingestion. AC-B2 (dedup), AC-G4 (signature), account resolution, handshake."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.inbox.models import InboundEvent
from app.inbox.payloads import ProcessInboundEventPayload
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.registry import JobContext, job_handler, registry_snapshot
from tests.factories import create_workspace
from tests.integration.inbox.conftest import APP_SECRET, WEBHOOK_PATH, InboxEnv


@pytest.fixture(autouse=True)
def _processing_stub() -> Iterator[None]:
    """The processing job arrives in P4-04; ingestion only needs the job type to exist."""
    with registry_snapshot():

        @job_handler("process_inbound_event", ProcessInboundEventPayload)
        def _noop(job: JobContext) -> None:
            return None

        yield


def events(session: Session) -> list[InboundEvent]:
    session.expire_all()
    return list(session.scalars(select(InboundEvent).order_by(InboundEvent.received_at)))


def queued_jobs(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).where(Job.job_type == "process_inbound_event")))


# --- AC-B1 / the happy path --------------------------------------------------------------------


def test_a_signed_message_is_stored_once_and_a_job_is_enqueued(inbox: InboxEnv) -> None:
    response = inbox.deliver("Aylık üyelik ne kadar?", mid="m-1")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    (event,) = events(inbox.session)
    assert event.status == "received"
    assert event.event_type == "message"
    assert event.workspace_id == inbox.env.workspace.id
    assert event.social_account_id == inbox.account.id
    assert event.dedup_key == "ig:mock-golkent:mid:m-1"
    assert event.is_simulated is True
    assert event.payload is not None and event.payload["message"]["mid"] == "m-1"

    (job,) = queued_jobs(inbox.session)
    assert job.workspace_id == inbox.env.workspace.id
    assert job.payload == {"event_id": str(event.id)}
    assert job.correlation_id == event.correlation_id


# --- AC-B2: deduplication ----------------------------------------------------------------------


def test_the_same_webhook_three_times_is_one_event_and_one_job(inbox: InboxEnv) -> None:
    payload = inbox.message_payload(mid="same-mid")
    for _ in range(3):
        assert inbox.post(payload).status_code == 200
    assert len(events(inbox.session)) == 1
    assert len(queued_jobs(inbox.session)) == 1


def test_a_batch_with_a_repeated_item_stores_it_once(inbox: InboxEnv) -> None:
    item = wf.message_item("mock-golkent", "cust-1", "dup", "hi", inbox.clock.now())
    other = wf.message_item("mock-golkent", "cust-1", "other", "hello", inbox.clock.now())
    payload = wf.build_payload("mock-golkent", inbox.clock.now(), item, other, item)
    assert inbox.post(payload).status_code == 200
    assert sorted(e.dedup_key for e in events(inbox.session)) == [
        "ig:mock-golkent:mid:dup",
        "ig:mock-golkent:mid:other",
    ]


def test_events_without_a_mid_deduplicate_by_content(inbox: InboxEnv) -> None:
    payload = wf.build_payload(
        "mock-golkent",
        inbox.clock.now(),
        wf.reaction_item("mock-golkent", "cust-1", "m-9", inbox.clock.now()),
    )
    inbox.post(payload)
    inbox.post(payload)
    (event,) = events(inbox.session)
    assert event.event_type == "reaction"
    assert event.dedup_key.startswith("ig:mock-golkent:reaction:")


# --- AC-G4: signatures -------------------------------------------------------------------------


def test_an_invalid_signature_is_401_stores_nothing_and_is_counted(inbox: InboxEnv) -> None:
    response = inbox.post(inbox.message_payload(), secret="not-the-secret")
    assert response.status_code == 401
    assert events(inbox.session) == []
    assert queued_jobs(inbox.session) == []

    rows = list(
        inbox.session.scalars(
            select(AuditLog).where(AuditLog.action == "webhook.signature_invalid")
        )
    )
    assert len(rows) == 1
    assert rows[0].workspace_id is None  # system-level
    assert rows[0].is_simulated is True
    assert rows[0].metadata_ == {"provider_kind": "mock"}  # no payload, no text


def test_a_missing_signature_is_401(inbox: InboxEnv) -> None:
    assert inbox.post(inbox.message_payload(), secret=None).status_code == 401
    assert events(inbox.session) == []


def test_the_signature_covers_the_raw_body(inbox: InboxEnv) -> None:
    payload = inbox.message_payload()
    body = wf.serialize(payload)
    signature = wf.sign(body, APP_SECRET)
    tampered = body.replace(b"cust-1", b"cust-2")
    response = inbox.webhook_client.post(
        WEBHOOK_PATH, content=tampered, headers={wf.SIGNATURE_HEADER: signature}
    )
    assert response.status_code == 401
    assert events(inbox.session) == []


def test_every_signature_failure_is_counted(inbox: InboxEnv) -> None:
    for _ in range(10):
        inbox.post(inbox.message_payload(), secret="wrong")
    count = inbox.session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "webhook.signature_invalid")
    )
    assert count == 10


# --- account resolution ------------------------------------------------------------------------


def test_an_unknown_receiving_account_is_stored_as_ignored_with_a_200(inbox: InboxEnv) -> None:
    response = inbox.post(inbox.message_payload(account_id="nobody-knows-me"))
    assert response.status_code == 200
    (event,) = events(inbox.session)
    assert (event.status, event.ignore_reason) == ("ignored", "UNKNOWN_ACCOUNT")
    assert event.workspace_id is None
    assert event.is_simulated is True  # taken from the path, not from an account
    assert queued_jobs(inbox.session) == []


def test_a_disconnected_account_is_ignored(inbox: InboxEnv) -> None:
    inbox.account.status = "disconnected"
    inbox.session.commit()
    inbox.deliver()
    (event,) = events(inbox.session)
    assert (event.status, event.ignore_reason) == ("ignored", "ACCOUNT_DISCONNECTED")
    assert queued_jobs(inbox.session) == []


def test_unsupported_shapes_are_stored_and_ignored(inbox: InboxEnv) -> None:
    payload = {
        "object": "instagram",
        "entry": [{"id": "mock-golkent", "messaging": [{"sender": {"id": "c"}, "weird": {}}]}],
    }
    assert inbox.post(payload).status_code == 200
    (event,) = events(inbox.session)
    assert (event.event_type, event.status, event.ignore_reason) == (
        "other",
        "ignored",
        "UNSUPPORTED_EVENT",
    )


def test_a_non_instagram_payload_after_a_valid_signature_is_a_quiet_200(inbox: InboxEnv) -> None:
    assert inbox.post({"object": "page", "entry": []}).status_code == 200
    assert events(inbox.session) == []


def test_a_body_that_is_not_json_is_a_quiet_200_after_a_valid_signature(inbox: InboxEnv) -> None:
    body = b"not json"
    response = inbox.webhook_client.post(
        WEBHOOK_PATH, content=body, headers={wf.SIGNATURE_HEADER: wf.sign(body, APP_SECRET)}
    )
    assert response.status_code == 200
    assert events(inbox.session) == []


def test_the_workspace_comes_from_the_account_and_the_provider_kind(inbox: InboxEnv) -> None:
    """A webhook for B's account never creates rows in A (and the kind must match the path)."""
    other = create_workspace(inbox.session, name="Other studio")
    inbox.session.add(
        SocialAccount(
            workspace_id=other.id,
            provider_kind="mock",
            external_account_id="mock-other",
            status="connected",
        )
    )
    inbox.session.add(
        SocialAccount(
            workspace_id=create_workspace(inbox.session, name="Real studio").id,
            provider_kind="meta",
            external_account_id="shared-external-id",
            status="connected",
        )
    )
    inbox.session.commit()

    inbox.post(inbox.message_payload(account_id="mock-other"))
    # the same external id, but registered under the other provider kind: not found via /mock
    inbox.post(inbox.message_payload(account_id="shared-external-id"))

    by_account = {e.dedup_key.split(":")[1]: e for e in events(inbox.session)}
    assert by_account["mock-other"].workspace_id == other.id
    assert by_account["mock-other"].workspace_id != inbox.env.workspace.id
    assert by_account["shared-external-id"].ignore_reason == "UNKNOWN_ACCOUNT"
    assert all(j.workspace_id == other.id for j in queued_jobs(inbox.session))


# --- routes ------------------------------------------------------------------------------------


def test_the_webhook_routes_are_not_under_the_session_api() -> None:
    assert WEBHOOK_PATH.startswith("/webhooks/") and not WEBHOOK_PATH.startswith("/api/")


def test_the_mock_endpoint_exists_only_when_the_mock_provider_is_enabled(
    build_app: Callable[..., Any], inbox: InboxEnv
) -> None:
    app = build_app(instagram_enabled_providers="meta", meta_app_secret=SecretStr("meta-secret"))
    body = wf.serialize(inbox.message_payload())
    with TestClient(app) as client:
        response = client.post(
            WEBHOOK_PATH, content=body, headers={wf.SIGNATURE_HEADER: wf.sign(body, APP_SECRET)}
        )
    assert response.status_code == 404
    assert events(inbox.session) == []


def test_the_meta_endpoint_needs_the_meta_secret_and_is_off_by_default(
    build_app: Callable[..., Any], inbox: InboxEnv
) -> None:
    body = wf.serialize(inbox.message_payload())
    default_app = build_app()
    with TestClient(default_app) as client:
        assert client.post("/webhooks/instagram", content=body).status_code in (404, 405)
    meta_app = build_app(
        instagram_enabled_providers="meta", meta_app_secret=SecretStr("meta-secret")
    )
    with TestClient(meta_app) as client:
        assert (
            client.post(
                "/webhooks/instagram",
                content=body,
                headers={wf.SIGNATURE_HEADER: wf.sign(body, "wrong")},
            ).status_code
            == 401
        )


def test_the_handshake_echoes_the_challenge_for_the_right_token(
    build_app: Callable[..., Any],
) -> None:
    app = build_app(
        instagram_enabled_providers="meta,mock",
        meta_app_secret=SecretStr("meta-secret"),
        meta_webhook_verify_token=SecretStr("the-token"),
    )
    with TestClient(app) as client:
        ok = client.get(
            "/webhooks/instagram",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "the-token",
                "hub.challenge": "1234",
            },
        )
        assert (ok.status_code, ok.text) == (200, "1234")
        for params in (
            {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1234"},
            {"hub.mode": "unsubscribe", "hub.verify_token": "the-token", "hub.challenge": "1234"},
            {"hub.mode": "subscribe", "hub.challenge": "1234"},
            {},
        ):
            assert client.get("/webhooks/instagram", params=params).status_code == 403
