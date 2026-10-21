"""AC-X7 for the Phase 6 invite flow (INV-10): the invite token is shown once, stored only as a
hash, and never reaches a log line, an audit entry, a notification or a job payload. The invite
response models are allow-lists without any token, secret or hash field."""

import json
import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import hash_token
from app.identity.models import Invite
from app.jobs.models import Job
from app.notifications.models import Notification
from tests.factories import login, workspace_with_members

SECRETISH = re.compile(r"password|secret|token|hash|cipher|api_key|credential", re.I)
BASE = "/api/v1/workspaces"


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    configure_logging(get_settings())  # undo the test's own configuration


@pytest.mark.invariant("INV-10")
def test_the_invite_response_models_are_allow_lists(app: FastAPI) -> None:
    schemas = app.openapi()["components"]["schemas"]
    expected = {
        # Shown once, to the person who created it: the link is the only place the token lives.
        "InviteOut": {"id", "role", "expires_at", "invite_path", "invite_url", "created_at"},
        # The listing never repeats the link.
        "PendingInviteOut": {"id", "role", "expires_at", "created_at"},
        "InviteAcceptOut": {"workspace_id", "workspace_name", "role"},
    }
    for name, fields in expected.items():
        properties = set(schemas[name]["properties"])
        assert properties == fields, name
        assert not [f for f in properties if SECRETISH.search(f)], name


@pytest.mark.invariant("INV-10")
@pytest.mark.usefixtures("restore_logging")
def test_the_invite_token_is_never_logged_audited_notified_or_queued(
    client: TestClient,
    db_session: Session,
    make_client: type[TestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(
        Settings(_env_file=None, app_env="development", log_format="json", log_level="DEBUG")
    )
    workspace, users = workspace_with_members(db_session)
    owner_headers = login(client, users["owner"])

    created = client.post(
        f"{BASE}/{workspace.id}/invites", json={"role": "staff"}, headers=owner_headers
    )
    assert created.status_code == 201
    token = created.json()["invite_path"].rsplit("/", 1)[-1]
    assert len(token) >= 40  # token_urlsafe(32)

    # A wrong token and the right one, from a signed-out browser.
    guest = make_client()  # type: ignore[operator]
    body = {
        "email": "new.person@example.test",
        "display_name": "New Person",
        "password": "pw-1234567890",
    }
    wrong = guest.post("/api/v1/invites/accept", json={"token": token[:-3] + "xyz", **body})
    assert wrong.status_code == 400 and wrong.json()["code"] == "INVITE_INVALID"
    accepted = guest.post("/api/v1/invites/accept", json={"token": token, **body})
    assert accepted.status_code in (200, 201)
    client.get(f"{BASE}/{workspace.id}/invites", headers=owner_headers)

    # Logs: some lines were written (so the check is not vacuous), none holds a token.
    logs = capsys.readouterr().err
    lines = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
    assert any(line.get("event") == "request" for line in lines)
    assert token not in logs and token[:-3] + "xyz" not in logs
    assert "pw-1234567890" not in logs

    # The database: only the hash of the token exists, and nowhere else is the token written.
    db_session.expire_all()
    (invite,) = db_session.scalars(select(Invite)).all()
    assert invite.token_hash == hash_token(token) and token.encode() not in bytes(invite.token_hash)
    for model in (AuditLog, Notification, Job):
        for row in db_session.scalars(select(model)):
            dumped = json.dumps(
                {c.name: str(getattr(row, c.key, "")) for c in model.__table__.columns}  # type: ignore[attr-defined]
            )
            assert token not in dumped, f"{model.__name__} holds the invite token"
