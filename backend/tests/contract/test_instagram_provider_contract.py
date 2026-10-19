"""Contract tests for the Instagram provider, messaging subset (integrations.md §3.5).

Run against the mock today; the Meta adapter (Phase 7) must satisfy the same expectations
with recorded fixtures. Covers: signatures, webhook parsing, sending in and out of the
window, the byte limit, and the error mapping of every injectable failure mode.
"""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
    ProviderWindowClosed,
)
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SimFailureRule, SimSentMessage, SocialAccount
from tests.factories import create_workspace

SECRET = "contract-test-secret"
CUSTOMER = "customer-1"


class Harness:
    def __init__(
        self, session: Session, factory: sessionmaker[Session], clock: FrozenClock
    ) -> None:
        self.session = session
        self.clock = clock
        workspace = create_workspace(session, name="Contract")
        self.account_row = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id="biz-1",
            username="biz.demo",
            status="connected",
        )
        session.add(self.account_row)
        session.commit()
        self.provider = MockInstagramProvider(factory, clock, SECRET)
        self.account = AccountRef(self.account_row.id, workspace.id, "biz-1")

    def customer_writes(self, *, at: datetime | None = None, customer: str = CUSTOMER) -> None:
        self.provider.record_simulated_inbound(
            self.account,
            customer,
            f"in-{customer}-{at or self.clock.now():%H%M%S}",
            at or self.clock.now(),
        )

    def fail(
        self,
        operation: str,
        mode: str,
        *,
        remaining: int | None = 1,
        retry_after: int | None = None,
    ) -> None:
        self.session.add(
            SimFailureRule(
                workspace_id=self.account.workspace_id,
                social_account_id=self.account.social_account_id,
                operation=operation,
                mode=mode,
                remaining=remaining,
                retry_after_s=retry_after,
            )
        )
        self.session.commit()

    def sent(self) -> list[SimSentMessage]:
        self.session.expire_all()
        return list(self.session.query(SimSentMessage).all())


@pytest.fixture
def h(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> Harness:
    return Harness(db_session, shared_session_factory, clock)


# --- signatures -----------------------------------------------------------------------------


def test_a_valid_signature_verifies(h: Harness) -> None:
    body = wf.serialize(wf.build_message_payload("biz-1", CUSTOMER, "m1", "hi", h.clock.now()))
    assert h.provider.verify_signature(body, wf.sign(body, SECRET))


def test_the_signature_format_is_meta_hmac_sha256(h: Harness) -> None:
    body = b'{"object":"instagram"}'
    expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert wf.sign(body, SECRET) == expected


@pytest.mark.parametrize(
    "header",
    [None, "", "sha256=", "sha256=deadbeef", "md5=abc", "SHA256=" + "0" * 64],
)
def test_missing_or_wrong_signatures_fail(h: Harness, header: str | None) -> None:
    body = b'{"object":"instagram"}'
    assert not h.provider.verify_signature(body, header)


def test_a_signature_of_a_different_body_or_secret_fails(h: Harness) -> None:
    body = b'{"object":"instagram","entry":[]}'
    assert not h.provider.verify_signature(body + b" ", wf.sign(body, SECRET))
    assert not h.provider.verify_signature(body, wf.sign(body, "another-secret"))


# --- parsing --------------------------------------------------------------------------------

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)


def test_a_customer_message_is_normalised(h: Harness) -> None:
    payload = wf.build_message_payload("biz-1", CUSTOMER, "m1", "Aylık üyelik ne kadar?", NOW)
    (event,) = h.provider.parse_webhook(payload)
    assert event.event_type == "message"
    assert (event.account_id, event.customer_id) == ("biz-1", CUSTOMER)
    assert event.mid == "m1"
    assert event.text == "Aylık üyelik ne kadar?"
    assert event.provider_timestamp == NOW
    assert event.is_echo is False


def test_an_echo_names_the_business_and_the_customer_the_right_way_round(h: Harness) -> None:
    payload = wf.build_echo_payload("biz-1", CUSTOMER, "e1", "Merhaba", NOW, app_id="app-9")
    (event,) = h.provider.parse_webhook(payload)
    assert event.event_type == "echo"
    assert event.is_echo is True
    assert (event.account_id, event.customer_id) == ("biz-1", CUSTOMER)
    assert event.app_id == "app-9"
    assert event.text == "Merhaba"


def test_attachments_are_normalised(h: Harness) -> None:
    payload = wf.build_message_payload(
        "biz-1",
        CUSTOMER,
        "m2",
        None,
        NOW,
        attachments=[{"type": "image", "url": "https://x/y.jpg"}],
    )
    (event,) = h.provider.parse_webhook(payload)
    assert event.text is None
    assert event.attachments == [{"type": "image", "url": "https://x/y.jpg", "note": None}]


def test_reaction_and_read_events_are_recognised(h: Harness) -> None:
    payload = wf.build_payload(
        "biz-1",
        NOW,
        wf.reaction_item("biz-1", CUSTOMER, "m1", NOW),
        wf.read_item("biz-1", CUSTOMER, "m1", NOW),
    )
    reaction, read = h.provider.parse_webhook(payload)
    assert (reaction.event_type, reaction.mid) == ("reaction", "m1")
    assert (read.event_type, read.mid) == ("read", "m1")


def test_unknown_shapes_become_other_and_are_not_dropped(h: Harness) -> None:
    payload = {
        "object": "instagram",
        "entry": [{"id": "biz-1", "messaging": [{"sender": {"id": CUSTOMER}, "mystery": {}}]}],
    }
    (event,) = h.provider.parse_webhook(payload)
    assert event.event_type == "other"
    assert event.account_id == "biz-1"


@pytest.mark.parametrize("payload", [{}, {"object": "page"}, {"object": "instagram"}, []])
def test_payloads_that_are_not_instagram_events_yield_nothing(h: Harness, payload: object) -> None:
    assert h.provider.parse_webhook(payload) == []  # type: ignore[arg-type]


def test_a_batch_yields_one_event_per_item(h: Harness) -> None:
    payload = wf.build_payload(
        "biz-1",
        NOW,
        wf.message_item("biz-1", CUSTOMER, "m1", "a", NOW),
        wf.message_item("biz-1", CUSTOMER, "m2", "b", NOW),
    )
    assert [e.mid for e in h.provider.parse_webhook(payload)] == ["m1", "m2"]


# --- sending --------------------------------------------------------------------------------


def test_sending_inside_the_window_stores_exactly_one_message(h: Harness) -> None:
    h.customer_writes()
    result = h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")
    (stored,) = h.sent()
    assert stored.message_id == result.message_id
    assert (stored.recipient_id, stored.text) == (CUSTOMER, "Merhaba")
    assert stored.sent_at == h.clock.now()


def test_sending_without_any_customer_message_is_a_closed_window(h: Harness) -> None:
    with pytest.raises(ProviderWindowClosed):
        h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")
    assert h.sent() == []


def test_the_window_is_per_recipient(h: Harness) -> None:
    h.customer_writes(customer="someone-else")
    with pytest.raises(ProviderWindowClosed):
        h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")


def test_the_window_closes_after_24_hours(h: Harness) -> None:
    h.customer_writes()
    h.clock.advance(timedelta(hours=23, minutes=59))
    h.provider.send_text_message(h.account, CUSTOMER, "still open")
    h.clock.advance(timedelta(minutes=2))
    with pytest.raises(ProviderWindowClosed):
        h.provider.send_text_message(h.account, CUSTOMER, "too late")


def test_a_new_customer_message_reopens_the_window(h: Harness) -> None:
    h.customer_writes(at=h.clock.now())
    h.clock.advance(timedelta(hours=30))
    h.customer_writes(at=h.clock.now())
    h.provider.send_text_message(h.account, CUSTOMER, "reopened")


def test_text_over_1000_bytes_is_rejected_and_1000_is_accepted(h: Harness) -> None:
    h.customer_writes()
    h.provider.send_text_message(h.account, CUSTOMER, "a" * 1000)
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.send_text_message(h.account, CUSTOMER, "a" * 1001)
    assert excinfo.value.request_code == "TEXT_TOO_LONG"


def test_the_limit_counts_bytes_not_characters(h: Harness) -> None:
    h.customer_writes()
    with pytest.raises(ProviderInvalidRequest):
        h.provider.send_text_message(h.account, CUSTOMER, "₺" * 400)  # 1200 bytes, 400 characters


def test_empty_text_is_rejected(h: Harness) -> None:
    h.customer_writes()
    with pytest.raises(ProviderInvalidRequest):
        h.provider.send_text_message(h.account, CUSTOMER, "   ")


# --- failure injection: error mapping ---------------------------------------------------------

MAPPING: list[tuple[str, type[Exception]]] = [
    ("transient", ProviderTransientError),
    ("rate_limited", ProviderRateLimited),
    ("auth_revoked", ProviderAuthError),
    ("permission_missing", ProviderPermissionError),
    ("window_closed", ProviderWindowClosed),
    ("invalid_media", ProviderInvalidRequest),
]


@pytest.mark.parametrize(("mode", "error"), MAPPING)
def test_each_failure_mode_maps_to_its_error_and_sends_nothing(
    h: Harness, mode: str, error: type[Exception]
) -> None:
    h.customer_writes()
    h.fail("send", mode)
    with pytest.raises(error):
        h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")
    assert h.sent() == []


def test_rate_limited_carries_retry_after(h: Harness) -> None:
    h.customer_writes()
    h.fail("send", "rate_limited", retry_after=45)
    with pytest.raises(ProviderRateLimited) as excinfo:
        h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")
    assert excinfo.value.retry_after_s == 45


def test_timeout_after_success_performs_the_effect_and_then_raises(h: Harness) -> None:
    h.customer_writes()
    h.fail("send", "timeout_after_success")
    with pytest.raises(ProviderOutcomeUnknown):
        h.provider.send_text_message(h.account, CUSTOMER, "Merhaba")
    assert [m.text for m in h.sent()] == ["Merhaba"]  # the message really went out


def test_a_rule_fires_remaining_times_and_then_stops(h: Harness) -> None:
    h.customer_writes()
    h.fail("send", "transient", remaining=2)
    for _ in range(2):
        with pytest.raises(ProviderTransientError):
            h.provider.send_text_message(h.account, CUSTOMER, "x")
    h.provider.send_text_message(h.account, CUSTOMER, "x")
    assert len(h.sent()) == 1


def test_a_rule_without_a_limit_fires_every_time(h: Harness) -> None:
    h.customer_writes()
    h.fail("send", "transient", remaining=None)
    for _ in range(5):
        with pytest.raises(ProviderTransientError):
            h.provider.send_text_message(h.account, CUSTOMER, "x")


def test_an_any_rule_applies_to_every_operation(h: Harness) -> None:
    h.fail("any", "transient", remaining=None)
    with pytest.raises(ProviderTransientError):
        h.provider.get_account_profile(h.account)
    with pytest.raises(ProviderTransientError):
        h.provider.find_recent_outbound(h.account, CUSTOMER, h.clock.now())


def test_a_rule_for_another_operation_is_ignored(h: Harness) -> None:
    h.customer_writes()
    h.fail("profile", "transient", remaining=None)
    h.provider.send_text_message(h.account, CUSTOMER, "ok")


# --- reads ----------------------------------------------------------------------------------


def test_the_profile_comes_from_the_connected_account(h: Harness) -> None:
    profile = h.provider.get_account_profile(h.account)
    assert (profile.external_account_id, profile.username) == ("biz-1", "biz.demo")


def test_find_recent_outbound_returns_what_was_sent_since(h: Harness) -> None:
    h.customer_writes()
    start = h.clock.now()
    h.provider.send_text_message(h.account, CUSTOMER, "first")
    h.clock.advance(timedelta(minutes=5))
    h.provider.send_text_message(h.account, CUSTOMER, "second")
    both = h.provider.find_recent_outbound(h.account, CUSTOMER, start)
    assert [m.text for m in both] == ["first", "second"]
    later = h.provider.find_recent_outbound(h.account, CUSTOMER, start + timedelta(minutes=1))
    assert [m.text for m in later] == ["second"]
    assert h.provider.find_recent_outbound(h.account, "nobody", start) == []


def test_the_lookup_can_be_made_unavailable(h: Harness) -> None:
    h.fail("lookup", "transient")
    with pytest.raises(ProviderTransientError):
        h.provider.find_recent_outbound(h.account, CUSTOMER, h.clock.now())


@pytest.mark.parametrize(
    "call",
    [
        lambda p, a: p.get_container_status(a, "c1"),
        lambda p, a: p.get_media(a, "m1"),
        lambda p, a: p.get_publishing_quota(a),
        lambda p, a: p.create_media_container(a, None),
        lambda p, a: p.publish_container(a, "c1"),
        lambda p, a: p.refresh_token(a),
    ],
)
def test_content_methods_are_not_available_yet(
    h: Harness, call: Callable[[MockInstagramProvider, AccountRef], object]
) -> None:
    with pytest.raises(NotImplementedError):
        call(h.provider, h.account)
