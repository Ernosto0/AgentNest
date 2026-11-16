"""F-01 part 2: what a push says. No customer text can reach a push service.

A push payload crosses a third party (the browser vendor's push service) and shows on a lock
screen, so it is built from a fixed template per notification type. These tests build the payload
of every supported type from notifications whose every field is stuffed with a distinctive
"customer" string and assert that the string, in every form it could take, never appears.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.clock import FrozenClock
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.web_push import payloads
from app.integrations.channels.web_push.payloads import build_payload, deep_link
from app.notifications.catalog import CATALOG, PUSH_CATEGORIES, PUSH_TYPES
from app.notifications.delivery_policy import evaluate_delivery_policy
from app.notifications.models import DELIVERY_STATUSES, Notification

CUSTOMER_TEXT = "ZZ-GIZLI-MUSTERI-MESAJI"
CUSTOMER_NAME = "Ayse Yilmaz"
CUSTOMER_HANDLE = "ayse_yilmaz_93"
DRAFT_TEXT = "Merhaba Ayse, uyelik 4.750 TL"
QUESTION_BODY = "Cumartesi 14:00 icin yer var mi diye soruyor musteri"
TITLE = "Yaz kampanyasi gizli baslik"
ALL_TEXT = (CUSTOMER_TEXT, CUSTOMER_NAME, CUSTOMER_HANDLE, DRAFT_TEXT, QUESTION_BODY, TITLE)

WORKSPACE = uuid.UUID("11111111-1111-4111-8111-111111111111")


def stuffed_params() -> dict[str, Any]:
    """Every key the app or an attacker could put customer text into, plus real ids."""
    return {
        "message": CUSTOMER_TEXT,
        "text": CUSTOMER_TEXT,
        "body": QUESTION_BODY,
        "title": TITLE,
        "summary": {"text": DRAFT_TEXT, "customer": CUSTOMER_NAME},
        "customer_name": CUSTOMER_NAME,
        "customer_handle": CUSTOMER_HANDLE,
        "username": CUSTOMER_HANDLE,
        "draft_text": DRAFT_TEXT,
        "caption": DRAFT_TEXT,
        "reason": CUSTOMER_TEXT,
        "action": CUSTOMER_TEXT,
        "url": f"https://evil.example/{CUSTOMER_TEXT}",
        "link_url": f"https://evil.example/{CUSTOMER_TEXT}",
        "question_id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "content_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
    }


def make(kind: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE,
        recipient_user_id=uuid.uuid4(),
        type=kind,
        severity=CATALOG[kind].severity,
        params=stuffed_params() if params is None else params,
        subject_id=uuid.uuid4(),
        is_simulated=kwargs.get("is_simulated", False),
    )


@pytest.mark.parametrize("locale", ["tr", "en", None, "de"])
@pytest.mark.parametrize("kind", sorted(PUSH_TYPES))
def test_no_customer_text_in_any_payload(kind: str, locale: str | None) -> None:
    payload = build_payload(make(kind), locale)
    text = payload.to_json()
    for secret in ALL_TEXT:
        assert secret not in text
        assert secret.lower() not in text.lower()
    for fragment in ("evil.example", "http"):
        assert fragment not in text
    assert set(json.loads(text)) == {"title", "body", "url", "tag"}


@pytest.mark.parametrize("kind", sorted(PUSH_TYPES))
def test_the_text_of_a_payload_is_independent_of_the_params(kind: str) -> None:
    """Only UUID ids can vary the link; the title and body never depend on params."""
    a = build_payload(make(kind, {}), "tr")
    b = build_payload(make(kind), "tr")
    assert (a.title, a.body) == (b.title, b.body)


@pytest.mark.parametrize("kind", sorted(PUSH_TYPES))
def test_the_link_is_a_same_origin_path_made_only_of_uuids(kind: str) -> None:
    link = deep_link(make(kind))
    assert link.startswith(f"/w/{WORKSPACE}") and "//" not in link and ":" not in link
    for part in link.removeprefix("/").replace("?account=", "/").split("/"):
        if len(part) == 36:
            uuid.UUID(part)


@pytest.mark.parametrize("bad", [CUSTOMER_TEXT, "../../etc/passwd", "javascript:alert(1)", "", 7])
def test_a_param_that_is_not_a_uuid_never_reaches_the_link(bad: Any) -> None:
    for kind, key in (
        ("owner_question.requested", "question_id"),
        ("content.failed", "content_id"),
        ("reply.failed", "conversation_id"),
    ):
        link = deep_link(make(kind, {key: bad, "account_id": bad}))
        assert link.startswith(f"/w/{WORKSPACE}/")
        assert ".." not in link and "javascript" not in link and CUSTOMER_TEXT not in link


def test_the_links_point_to_the_right_pages() -> None:
    q, a, c, v = (str(uuid.uuid4()) for _ in range(4))
    base = f"/w/{WORKSPACE}"
    assert deep_link(make("approval.requested", {})) == f"{base}/approvals"
    assert (
        deep_link(make("owner_question.requested", {"question_id": q, "account_id": a}))
        == f"{base}/more/agent/questions/{q}?account={a}"
    )
    assert deep_link(make("content.failed", {"content_id": c})) == f"{base}/content/{c}"
    assert deep_link(make("content.failed", {})) == f"{base}/content"
    assert deep_link(make("reply.failed", {"conversation_id": v})) == f"{base}/inbox/{v}"
    assert deep_link(make("account.needs_reauth", {})) == f"{base}/more/settings/connections"


def test_every_supported_type_has_text_in_both_languages_and_a_category() -> None:
    assert set(payloads._TEXT) == set(PUSH_TYPES)
    assert set(PUSH_TYPES.values()) == set(PUSH_CATEGORIES)
    for kind, texts in payloads._TEXT.items():
        assert set(texts) == {"en", "tr"}, kind
        for title, body in texts.values():
            assert title and body and len(title) < 80 and len(body) < 120


def test_locale_picks_the_language() -> None:
    assert build_payload(make("approval.requested"), "tr").title == "Onayınız bekleniyor"
    assert build_payload(make("approval.requested"), "en").title == "Approval needed"
    assert build_payload(make("approval.requested"), "tr-TR").title == "Onayınız bekleniyor"


def test_a_simulated_notification_is_marked_in_the_title() -> None:
    plain = build_payload(make("approval.requested"), "en")
    simulated = build_payload(make("approval.requested", is_simulated=True), "en")
    assert simulated.title == "[Simulation] " + plain.title
    tr = build_payload(make("approval.requested", is_simulated=True), "tr")
    assert tr.title.startswith("[Simülasyon] ")


def test_a_type_that_is_not_pushable_is_an_error_never_a_generic_fallback() -> None:
    for kind in set(CATALOG) - set(PUSH_TYPES):
        with pytest.raises(ValueError):
            build_payload(make(kind), "en")


def test_the_tag_names_the_notification_so_a_resend_replaces_instead_of_stacking() -> None:
    n = make("approval.requested")
    assert build_payload(n, "en").tag == f"approval.requested:{n.id}"


def test_the_payload_is_small() -> None:
    for kind in PUSH_TYPES:
        assert len(build_payload(make(kind), "tr").to_json().encode()) < payloads.MAX_PAYLOAD_BYTES


@pytest.mark.parametrize("kind", sorted(PUSH_TYPES))
def test_the_delivery_policy_gives_every_supported_type_a_ledger_status(kind: str) -> None:
    """The ledger's CHECK constraint accepts only some statuses; the policy must never return
    ``web_only`` (or anything else) for a type we push."""
    for hour in (12, 20):  # 15:00 and 23:00 in Istanbul
        clock = FrozenClock(datetime(2026, 1, 15, hour, 0, tzinfo=UTC))
        recipient = ChannelRecipient(
            user_id=uuid.uuid4(),
            workspace_id=WORKSPACE,
            channel="web_push",
            timezone="Europe/Istanbul",
        )
        decision = evaluate_delivery_policy(make(kind), recipient, clock, channel="web_push")
        assert decision.status in DELIVERY_STATUSES
