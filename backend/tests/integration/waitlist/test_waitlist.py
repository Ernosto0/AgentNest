"""P-06: the public pilot waitlist (POST /api/v1/waitlist)."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import BACKEND_DIR
from app.core.email import email_outbox
from app.retention import cleanup
from app.waitlist import service
from app.waitlist.models import WaitlistEntry

URL = "/api/v1/waitlist"
LANDING = "https://landing.example"
OPERATOR = "ops@example.com"


@pytest.fixture(autouse=True)
def _clean_outbox() -> None:
    email_outbox.clear()


@pytest.fixture
def waitlist_client(build_app: Callable[..., FastAPI]) -> TestClient:
    app = build_app(operator_alert_email=OPERATOR, landing_origins=LANDING)
    return TestClient(app)


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(WaitlistEntry)) or 0


def test_submission_is_stored_and_emailed_to_the_operator(
    waitlist_client: TestClient, db_session: Session
) -> None:
    response = waitlist_client.post(
        URL,
        json={
            "email": " Owner@Studio.Example ",
            "business_name": "Gölkent Pilates",
            "category": "Pilates",
            "instagram_handle": "golkentpilates",
            "city": "Ankara",
            "locale": "tr",
        },
    )
    assert response.status_code == 202
    assert response.json() == {"status": "received"}
    entry = db_session.scalars(select(WaitlistEntry)).one()
    assert entry.email == "owner@studio.example"
    assert entry.business_name == "Gölkent Pilates"
    assert entry.locale == "tr"
    [mail] = email_outbox.get_messages()
    assert mail.to_email == OPERATOR
    assert "owner@studio.example" in mail.text_body
    assert "Gölkent Pilates" in mail.text_body
    assert "owner@studio.example" not in mail.subject  # no personal data in the subject


def test_business_name_is_optional(waitlist_client: TestClient, db_session: Session) -> None:
    response = waitlist_client.post(URL, json={"email": "a@b.example", "business_name": "  "})
    assert response.status_code == 202
    assert db_session.scalars(select(WaitlistEntry)).one().business_name is None


def test_a_repeated_email_is_idempotent_and_sends_one_notice(
    waitlist_client: TestClient, db_session: Session
) -> None:
    first = waitlist_client.post(URL, json={"email": "Same@Example.com"})
    second = waitlist_client.post(URL, json={"email": "same@example.com", "city": "Izmir"})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()  # nothing reveals that the email was already known
    assert count(db_session) == 1
    assert len(email_outbox.get_messages()) == 1
    assert db_session.scalars(select(WaitlistEntry)).one().city is None  # first entry kept


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "not-an-email"},
        {"email": "a@b"},
        {"email": "two@@example.com"},
        {"email": "sp ace@example.com"},
        {"email": "a..b@example.com"},
        {"email": "a@example.com\nBcc: x@y.example"},
        {"email": "a@example.com", "locale": "de"},
        {"email": "a@example.com", "business_name": "x" * 500},
        {"email": "a@example.com", "business_name": "line\nbreak"},
        {"email": "a@example.com", "unknown_field": "x"},
    ],
)
def test_invalid_bodies_are_rejected_and_not_stored(
    waitlist_client: TestClient, db_session: Session, payload: dict[str, object]
) -> None:
    response = waitlist_client.post(URL, json=payload)
    assert response.status_code == 422
    assert count(db_session) == 0
    assert email_outbox.get_messages() == []


def test_submissions_are_rate_limited_per_client(
    waitlist_client: TestClient, db_session: Session
) -> None:
    for i in range(5):
        assert waitlist_client.post(URL, json={"email": f"p{i}@example.com"}).status_code == 202
    blocked = waitlist_client.post(URL, json={"email": "p9@example.com"})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) > 0
    assert count(db_session) == 5


def test_the_email_is_never_logged_in_plain_text(
    waitlist_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "private.person@hidden-domain.example"
    with caplog.at_level(logging.DEBUG):
        waitlist_client.post(URL, json={"email": secret})
    assert "waitlist_submission" in caplog.text
    assert secret not in caplog.text
    assert "hidden-domain" not in caplog.text


def test_a_failing_mail_transport_does_not_fail_the_request(
    waitlist_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("smtp down")

    monkeypatch.setattr(service, "send_email", boom)
    response = waitlist_client.post(URL, json={"email": "kept@example.com"})
    assert response.status_code == 202
    assert count(db_session) == 1  # stored; `waitlist-list` still shows it


def test_without_an_operator_address_the_entry_is_stored_and_nothing_is_sent(
    build_app: Callable[..., FastAPI], db_session: Session
) -> None:
    client = TestClient(build_app(operator_alert_email=""))
    assert client.post(URL, json={"email": "quiet@example.com"}).status_code == 202
    assert count(db_session) == 1
    assert email_outbox.get_messages() == []


# --- CORS for the landing origin -------------------------------------------------------------


def test_the_landing_origin_may_preflight_and_post(waitlist_client: TestClient) -> None:
    preflight = waitlist_client.options(
        URL,
        headers={
            "Origin": LANDING,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == LANDING
    assert "access-control-allow-credentials" not in preflight.headers
    posted = waitlist_client.post(URL, json={"email": "c@example.com"}, headers={"Origin": LANDING})
    assert posted.status_code == 202
    assert posted.headers["access-control-allow-origin"] == LANDING


def test_other_origins_and_other_routes_get_no_cors_headers(
    waitlist_client: TestClient,
) -> None:
    other = waitlist_client.post(
        URL, json={"email": "d@example.com"}, headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in other.headers
    meta = waitlist_client.get("/api/v1/meta", headers={"Origin": LANDING})
    assert "access-control-allow-origin" not in meta.headers


def test_without_landing_origins_nothing_is_allowed(
    build_app: Callable[..., FastAPI],
) -> None:
    client = TestClient(build_app(landing_origins=""))
    response = client.post(URL, json={"email": "e@example.com"}, headers={"Origin": LANDING})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("bad", ["*", "landing.example", "https://landing.example/path"])
def test_landing_origins_must_be_plain_origins(settings: Settings, bad: str) -> None:
    problems = settings.model_copy(update={"landing_origins": bad}).safety_problems()
    assert any("LANDING_ORIGINS" in p for p in problems)


# --- retention, deletion on request ------------------------------------------------------------


def test_retention_deletes_old_entries_only(
    db_session: Session, shared_session_factory: sessionmaker[Session], settings: Settings
) -> None:
    now = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
    days = settings.retention_waitlist_days
    for email, age in (("old@example.com", days + 1), ("new@example.com", days - 1)):
        db_session.add(
            WaitlistEntry(
                email=email,
                email_normalized=email,
                locale="tr",
                created_at=now - timedelta(days=age),
            )
        )
    db_session.commit()
    counts = cleanup.run_retention(shared_session_factory, settings, now)
    assert counts.waitlist_deleted == 1
    db_session.expire_all()
    assert db_session.scalars(select(WaitlistEntry.email)).all() == ["new@example.com"]


def test_delete_on_request_removes_the_entry(db_session: Session) -> None:
    db_session.add(WaitlistEntry(email="Gone@Example.com", email_normalized="gone@example.com"))
    db_session.commit()
    assert service.delete_by_email(db_session, " GONE@example.com ") == 1
    assert service.delete_by_email(db_session, "gone@example.com") == 0
    assert service.list_entries(db_session) == []


# --- migration -----------------------------------------------------------------------------------


def test_migration_0049_upgrades_and_downgrades_cleanly(engine: Engine) -> None:
    schema = "waitlist_mig_" + uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    try:
        command.upgrade(config, "0048")
        with isolated.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('waitlist_entries')")) is None
        command.upgrade(config, "0049")
        with isolated.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO waitlist_entries (id, email, email_normalized) "
                    "VALUES (:id, 'a@b.example', 'a@b.example')"
                ),
                {"id": uuid.uuid4()},
            )
        command.downgrade(config, "0048")
        with isolated.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('waitlist_entries')")) is None
        command.upgrade(config, "0049")  # and back up again
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
