"""Contract tests for the Instagram provider (integrations.md §3.5).

Shared adapter-neutral cases run against mock and synthetic offline Meta.
Simulator-specific persistence and failure-rule assertions remain intact. Covers:
signatures, webhook parsing, sending in and out of the
window, the byte limit, the publishing lifecycle (container, publish, expiry, quota) and the
error mapping of every injectable failure mode.
"""

import hashlib
import hmac
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.base import AccountRef, ContainerSpec
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
    ProviderWindowClosed,
)
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import (
    SimContainer,
    SimFailureRule,
    SimPublishedMedia,
    SimSentMessage,
    SocialAccount,
)
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from tests.factories import create_workspace
from tests.helpers.images import png_bytes

SECRET = "contract-test-secret"
CUSTOMER = "customer-1"
CONTAINER_DELAY_S = 2
DAILY_LIMIT = 3


class Harness:
    def __init__(
        self,
        session: Session,
        factory: sessionmaker[Session],
        clock: FrozenClock,
        media_root: Path,
    ) -> None:
        self.session = session
        self.clock = clock
        self.factory = factory
        self.storage = LocalMediaStorage(media_root, clock)
        workspace = create_workspace(session, name="Contract")
        self.workspace_id = workspace.id
        self.account_row = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id="biz-1",
            username="biz.demo",
            status="connected",
        )
        session.add(self.account_row)
        session.commit()
        self.provider = MockInstagramProvider(
            factory,
            clock,
            SECRET,
            storage=self.storage,
            container_delay_s=CONTAINER_DELAY_S,
            daily_publish_limit=DAILY_LIMIT,
        )
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

    # --- publishing helpers ---

    def image_url(self, data: bytes | None = None, *, ttl_s: int = 3600) -> str:
        """Store an image and return the ``localmedia:`` reference the mock is given."""
        key = build_key(self.workspace_id, uuid.uuid4(), self.clock.now())
        self.storage.put(key, io.BytesIO(data or jpeg_bytes()), "image/jpeg")
        return self.storage.public_fetch_url(key, ttl_s)

    def container(self, media_type: str = "IMAGE", caption: str | None = "Merhaba") -> str:
        spec = ContainerSpec(media_type, self.image_url(), caption)  # type: ignore[arg-type]
        return self.provider.create_media_container(self.account, spec)

    def finished_container(self, media_type: str = "IMAGE") -> str:
        container_id = self.container(media_type, None if media_type == "STORIES" else "Merhaba")
        self.clock.advance(seconds=CONTAINER_DELAY_S)
        return container_id

    def published(self) -> list[SimPublishedMedia]:
        self.session.expire_all()
        return list(self.session.query(SimPublishedMedia).all())

    def containers(self) -> list[SimContainer]:
        self.session.expire_all()
        return list(self.session.query(SimContainer).all())


def jpeg_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1080, 1350), "navy").save(out, "JPEG")
    return out.getvalue()


@pytest.fixture
def h(
    db_session: Session,
    shared_session_factory: sessionmaker[Session],
    clock: FrozenClock,
    tmp_path: Path,
) -> Harness:
    return Harness(db_session, shared_session_factory, clock, tmp_path / "media")


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


def test_refreshing_a_token_is_not_available_on_the_mock(h: Harness) -> None:
    with pytest.raises(NotImplementedError):
        h.provider.refresh_token(h.account)


# --- publishing: container lifecycle ----------------------------------------------------------


def test_a_container_goes_from_in_progress_to_finished_to_published(h: Harness) -> None:
    container_id = h.container()
    assert h.provider.get_container_status(h.account, container_id).status_code == "IN_PROGRESS"
    h.clock.advance(seconds=CONTAINER_DELAY_S - 1)
    assert h.provider.get_container_status(h.account, container_id).status_code == "IN_PROGRESS"
    h.clock.advance(seconds=1)
    finished = h.provider.get_container_status(h.account, container_id)
    assert (finished.status_code, finished.media_id) == ("FINISHED", None)

    media_id = h.provider.publish_container(h.account, container_id)

    published = h.provider.get_container_status(h.account, container_id)
    assert published.status_code == "PUBLISHED"
    assert published.media_id == media_id  # lets reconciliation find the post after a lost answer
    (row,) = h.published()
    assert (row.media_id, row.container_id) == (media_id, container_id)
    assert row.published_at == h.clock.now()


def test_a_new_container_records_its_deadlines_and_what_it_was_given(h: Harness) -> None:
    start = h.clock.now()
    container_id = h.container(caption="Yeni sezon")
    (row,) = h.containers()
    assert row.container_id == container_id
    assert (row.media_type, row.caption, row.status) == ("IMAGE", "Yeni sezon", "IN_PROGRESS")
    assert row.ready_at == start + timedelta(seconds=CONTAINER_DELAY_S)
    assert row.expires_at == start + timedelta(hours=24)
    assert row.media_url.startswith("localmedia:")
    assert (row.workspace_id, row.social_account_id) == (h.workspace_id, h.account_row.id)


def test_publishing_before_the_container_is_finished_is_rejected(h: Harness) -> None:
    container_id = h.container()
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.publish_container(h.account, container_id)
    assert excinfo.value.request_code == "CONTAINER_NOT_READY"
    assert h.published() == []
    h.clock.advance(seconds=CONTAINER_DELAY_S)  # and works once it is ready
    h.provider.publish_container(h.account, container_id)
    assert len(h.published()) == 1


def test_publishing_a_container_twice_is_rejected_and_creates_one_post(h: Harness) -> None:
    container_id = h.finished_container()
    first = h.provider.publish_container(h.account, container_id)
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.publish_container(h.account, container_id)
    assert excinfo.value.request_code == "CONTAINER_PUBLISHED"
    assert [m.media_id for m in h.published()] == [first]


def test_the_database_refuses_a_second_post_for_one_container(h: Harness) -> None:
    """The backstop under the status check: ``unique(container_id)`` (a race cannot double-post)."""
    container_id = h.finished_container()
    h.provider.publish_container(h.account, container_id)
    h.session.add(
        SimPublishedMedia(
            workspace_id=h.workspace_id,
            social_account_id=h.account_row.id,
            media_id="mock-media-other",
            container_id=container_id,
            permalink="https://instagram.example/sim/mock-media-other",
            published_at=h.clock.now(),
        )
    )
    with pytest.raises(IntegrityError):
        h.session.flush()
    h.session.rollback()


def test_an_unpublished_container_expires_after_24_hours(h: Harness) -> None:
    container_id = h.container()
    h.clock.advance(hours=23, minutes=59)
    assert h.provider.get_container_status(h.account, container_id).status_code == "FINISHED"
    h.clock.advance(minutes=1)
    assert h.provider.get_container_status(h.account, container_id).status_code == "EXPIRED"
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.publish_container(h.account, container_id)
    assert excinfo.value.request_code == "CONTAINER_EXPIRED"
    assert h.published() == []


def test_a_published_container_stays_published_after_24_hours(h: Harness) -> None:
    container_id = h.finished_container()
    h.provider.publish_container(h.account, container_id)
    h.clock.advance(hours=48)
    assert h.provider.get_container_status(h.account, container_id).status_code == "PUBLISHED"


def test_a_story_container_is_created_without_a_caption(h: Harness) -> None:
    container_id = h.finished_container("STORIES")
    h.provider.publish_container(h.account, container_id)
    (row,) = h.containers()
    assert (row.media_type, row.caption) == ("STORIES", None)


def test_a_story_with_a_caption_is_rejected(h: Harness) -> None:
    spec = ContainerSpec("STORIES", h.image_url(), "text on a story")
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, spec)
    assert excinfo.value.request_code == "CAPTION_NOT_ALLOWED"
    assert h.containers() == []


@pytest.mark.parametrize(
    "image_url",
    ["https://example.com/a.jpg", "localmedia:not-a-key?exp=9999999999", "localmedia:no-expiry"],
)
def test_an_image_url_that_is_not_a_fetch_reference_is_rejected(h: Harness, image_url: str) -> None:
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, ContainerSpec("IMAGE", image_url, "x"))
    assert excinfo.value.request_code == "MEDIA_REJECTED"
    assert h.containers() == []


def test_an_image_that_is_not_a_jpeg_is_rejected(h: Harness) -> None:
    spec = ContainerSpec("IMAGE", h.image_url(png_bytes()), "x")
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, spec)
    assert excinfo.value.request_code == "MEDIA_REJECTED"
    assert h.containers() == []


def test_an_image_that_is_not_in_the_storage_is_rejected(h: Harness) -> None:
    key = build_key(h.workspace_id, uuid.uuid4(), h.clock.now())
    spec = ContainerSpec("IMAGE", h.storage.public_fetch_url(key, 3600), "x")
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, spec)
    assert excinfo.value.request_code == "MEDIA_REJECTED"


def test_an_expired_fetch_reference_is_rejected(h: Harness) -> None:
    url = h.image_url(ttl_s=60)
    h.clock.advance(seconds=61)
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, ContainerSpec("IMAGE", url, "x"))
    assert excinfo.value.request_code == "MEDIA_REJECTED"


def test_an_unknown_container_or_media_is_an_invalid_request(h: Harness) -> None:
    for call in (
        lambda: h.provider.get_container_status(h.account, "nope"),
        lambda: h.provider.publish_container(h.account, "nope"),
        lambda: h.provider.get_media(h.account, "nope"),
    ):
        with pytest.raises(ProviderInvalidRequest):
            call()


def test_another_account_cannot_see_or_publish_a_container(h: Harness) -> None:
    other_workspace = create_workspace(h.session, name="Other")
    other_row = SocialAccount(
        workspace_id=other_workspace.id,
        provider_kind="mock",
        external_account_id="biz-2",
        status="connected",
    )
    h.session.add(other_row)
    h.session.commit()
    other = AccountRef(other_row.id, other_workspace.id, "biz-2")
    container_id = h.finished_container()
    media_id = h.provider.publish_container(h.account, container_id)

    with pytest.raises(ProviderInvalidRequest):
        h.provider.get_container_status(other, container_id)
    with pytest.raises(ProviderInvalidRequest):
        h.provider.publish_container(other, container_id)
    with pytest.raises(ProviderInvalidRequest):
        h.provider.get_media(other, media_id)
    assert h.provider.get_publishing_quota(other).used == 0


# --- publishing: media and quota --------------------------------------------------------------


def test_the_published_media_has_a_clearly_fake_permalink(h: Harness) -> None:
    container_id = h.finished_container()
    media_id = h.provider.publish_container(h.account, container_id)
    info = h.provider.get_media(h.account, media_id)
    assert info.media_id == media_id
    assert info.permalink == f"https://instagram.example/sim/{media_id}"
    assert info.timestamp == h.clock.now()


def test_the_quota_counts_the_posts_of_the_last_24_hours(h: Harness) -> None:
    quota = h.provider.get_publishing_quota(h.account)
    assert (quota.used, quota.limit, quota.window_hours) == (0, DAILY_LIMIT, 24)
    h.provider.publish_container(h.account, h.finished_container())
    h.clock.advance(hours=1)
    h.provider.publish_container(h.account, h.finished_container())
    assert h.provider.get_publishing_quota(h.account).used == 2
    h.clock.advance(hours=23)  # the first post is now 24 h old and leaves the window
    assert h.provider.get_publishing_quota(h.account).used == 1
    h.clock.advance(hours=1)
    assert h.provider.get_publishing_quota(h.account).used == 0


def test_the_default_limit_is_fifty(
    shared_session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    provider = MockInstagramProvider(shared_session_factory, clock, SECRET)
    quota = provider.get_publishing_quota(AccountRef(uuid.uuid4(), uuid.uuid4(), "x"))
    assert (quota.used, quota.limit) == (0, 50)


def test_publishing_beyond_the_limit_is_rate_limited_until_the_oldest_post_leaves(
    h: Harness,
) -> None:
    for _ in range(DAILY_LIMIT):
        h.provider.publish_container(h.account, h.finished_container())
        h.clock.advance(minutes=10)
    container_id = h.finished_container()
    with pytest.raises(ProviderRateLimited) as excinfo:
        h.provider.publish_container(h.account, container_id)
    # the oldest post is DAILY_LIMIT * (10 min + 2 s) old
    assert excinfo.value.retry_after_s == 24 * 3600 - DAILY_LIMIT * (600 + CONTAINER_DELAY_S)
    assert len(h.published()) == DAILY_LIMIT
    h.clock.advance(seconds=excinfo.value.retry_after_s or 0)
    h.provider.publish_container(h.account, container_id)
    assert len(h.published()) == DAILY_LIMIT + 1


# --- publishing: failure injection ------------------------------------------------------------

CONTAINER_OPERATIONS = ["create_container", "container_status", "publish"]


def call_operation(h: Harness, operation: str, container_id: str | None = None) -> object:
    """Invoke one of the three publishing operations (on a finished container if it needs one)."""
    if operation == "create_container":
        return h.provider.create_media_container(
            h.account, ContainerSpec("IMAGE", h.image_url(), "x")
        )
    container_id = container_id or h.finished_container()
    if operation == "container_status":
        return h.provider.get_container_status(h.account, container_id)
    return h.provider.publish_container(h.account, container_id)


@pytest.mark.parametrize("operation", CONTAINER_OPERATIONS)
@pytest.mark.parametrize(
    ("mode", "error"),
    [
        ("transient", ProviderTransientError),
        ("rate_limited", ProviderRateLimited),
        ("auth_revoked", ProviderAuthError),
    ],
)
def test_transient_rate_limited_and_auth_revoked_apply_to_all_three_operations(
    h: Harness, operation: str, mode: str, error: type[Exception]
) -> None:
    container_id = h.finished_container() if operation != "create_container" else None
    containers_before = len(h.containers())
    h.fail(operation, mode)
    with pytest.raises(error):
        call_operation(h, operation, container_id)
    assert h.published() == []  # nothing went out
    assert len(h.containers()) == containers_before  # and no container appeared
    call_operation(h, operation, container_id)  # the rule is spent: the next call works


@pytest.mark.parametrize("operation", CONTAINER_OPERATIONS)
def test_rate_limited_carries_retry_after_on_the_publishing_operations(
    h: Harness, operation: str
) -> None:
    h.fail(operation, "rate_limited", retry_after=77)
    with pytest.raises(ProviderRateLimited) as excinfo:
        call_operation(h, operation)
    assert excinfo.value.retry_after_s == 77


def test_invalid_media_on_create_container_is_media_rejected(h: Harness) -> None:
    h.fail("create_container", "invalid_media")
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.create_media_container(h.account, ContainerSpec("IMAGE", h.image_url(), "x"))
    assert excinfo.value.request_code == "MEDIA_REJECTED"
    assert h.containers() == []


def test_invalid_media_on_container_status_is_an_error_status_that_sticks(h: Harness) -> None:
    container_id = h.container()
    h.fail("container_status", "invalid_media")
    status = h.provider.get_container_status(h.account, container_id)
    assert status.status_code == "ERROR" and status.error_detail
    h.clock.advance(seconds=CONTAINER_DELAY_S)  # the rule is spent, the container stays failed
    assert h.provider.get_container_status(h.account, container_id).status_code == "ERROR"
    with pytest.raises(ProviderInvalidRequest) as excinfo:
        h.provider.publish_container(h.account, container_id)
    assert excinfo.value.request_code == "CONTAINER_ERROR"
    assert h.published() == []


def test_timeout_after_success_on_publish_posts_once_and_then_raises(h: Harness) -> None:
    container_id = h.finished_container()
    h.fail("publish", "timeout_after_success")
    with pytest.raises(ProviderOutcomeUnknown):
        h.provider.publish_container(h.account, container_id)
    (post,) = h.published()  # the post really went out
    assert post.container_id == container_id
    # Reconciliation sees it and must not publish again (INV-06).
    assert h.provider.get_container_status(h.account, container_id).status_code == "PUBLISHED"
    with pytest.raises(ProviderInvalidRequest):
        h.provider.publish_container(h.account, container_id)
    assert len(h.published()) == 1


def test_an_any_rule_reaches_the_publishing_operations(h: Harness) -> None:
    h.fail("any", "transient", remaining=None)
    for operation in CONTAINER_OPERATIONS:
        with pytest.raises(ProviderTransientError):
            call_operation(h, operation, "mock-container-x")


def test_a_rule_for_another_operation_does_not_touch_publishing(h: Harness) -> None:
    h.fail("send", "transient", remaining=None)
    h.provider.publish_container(h.account, h.finished_container())
    assert len(h.published()) == 1


# --- shared adapter-neutral contract (mock + synthetic offline Meta) ---------------------------

META_FIXTURES = Path(__file__).parent / "fixtures" / "meta"


def meta_fixture(name):
    return json.loads((META_FIXTURES / f"{name}.json").read_text())


class OfflineMetaHarness:
    """Deterministic remote state served by labelled JSON fixture shapes, no live calls."""

    def __init__(self, clock):
        self.clock = clock
        self.account = AccountRef(
            uuid.uuid4(), uuid.uuid4(), "biz-1", lambda: "synthetic-contract-token"
        )
        self.provider = MetaInstagramProvider(
            clock, SECRET, "v25.0", transport=httpx.MockTransport(self.handle)
        )
        self.inbound = {}
        self.sent_messages = []
        self.container_times = {}
        self.published_ids = {}
        self.failure = None
        self.next_id = 0

    def customer_writes(self, *, at=None, customer=CUSTOMER):
        self.inbound[customer] = at or self.clock.now()

    def fail(self, operation, mode, **kwargs):
        self.failure = mode, kwargs.get("retry_after", 45)

    def image_url(self):
        return "https://example.test/synthetic.jpg"

    def container(self):
        return self.provider.create_media_container(
            self.account, ContainerSpec("IMAGE", self.image_url(), "Merhaba")
        )

    def handle(self, request):
        path = request.url.path.split("/")[-1]
        body = json.loads(request.content) if request.content else {}
        failure, self.failure = self.failure, None
        timeout = failure and failure[0] == "timeout_after_success"
        if failure and not timeout:
            mode, retry = failure
            if mode == "transient":
                raise httpx.ConnectError("synthetic connection refused", request=request)
            mapping = {
                "auth_revoked": "auth_expired_190",
                "permission_missing": "permission_10",
                "window_closed": "window_closed_2534022",
                "invalid_media": "invalid_media_36000",
                "rate_limited": "rate_limit_4",
            }
            return httpx.Response(
                400,
                json=meta_fixture("error_" + mapping[mode]),
                headers={"Retry-After": str(retry)},
            )
        self.next_id += 1
        if path == "messages" and request.method == "POST":
            recipient = body["recipient"]["id"]
            if recipient not in self.inbound or self.clock.now() >= self.inbound[
                recipient
            ] + timedelta(hours=24):
                return httpx.Response(400, json=meta_fixture("error_window_closed_2534022"))
            data = meta_fixture("send_ok")
            data["message_id"] = f"meta-mid-{self.next_id}"
            self.sent_messages.append(
                {
                    "id": data["message_id"],
                    "from": {"id": "biz-1"},
                    "to": {"data": [{"id": recipient}]},
                    "message": body["message"]["text"],
                    "created_time": self.clock.now().isoformat(),
                }
            )
        elif path == "conversations":
            data = meta_fixture("conversations_messages_ok")
            data["data"][0]["messages"]["data"] = self.sent_messages
        elif path == "media":
            data = meta_fixture("container_create_ok")
            data["id"] = f"container-{self.next_id}"
            self.container_times[data["id"]] = self.clock.now()
        elif path == "media_publish":
            cid = body["creation_id"]
            if (
                cid in self.published_ids
                or cid not in self.container_times
                or self.clock.now()
                < self.container_times[cid] + timedelta(seconds=CONTAINER_DELAY_S)
                or self.clock.now() >= self.container_times[cid] + timedelta(hours=24)
            ):
                return httpx.Response(400, json=meta_fixture("error_invalid_request_100"))
            data = meta_fixture("publish_ok")
            data["id"] = f"media-{self.next_id}"
            self.published_ids[cid] = data["id"]
        elif path in self.container_times:
            status = (
                "published"
                if path in self.published_ids
                else "expired"
                if self.clock.now() >= self.container_times[path] + timedelta(hours=24)
                else "finished"
                if self.clock.now()
                >= self.container_times[path] + timedelta(seconds=CONTAINER_DELAY_S)
                else "in_progress"
            )
            data = meta_fixture("container_status_" + status)
        elif path in self.published_ids.values():
            data = meta_fixture("media_ok")
            data["id"] = path
        elif path == "content_publishing_limit":
            data = meta_fixture("publishing_limit_ok")
            data["data"][0]["quota_usage"] = len(self.published_ids)
        else:
            data = meta_fixture("profile_ok")
        if timeout:
            raise httpx.ReadTimeout("synthetic accepted; response lost", request=request)
        return httpx.Response(200, json=data)


@pytest.fixture(params=["mock", "meta"])
def shared(request, h, clock):
    return h if request.param == "mock" else OfflineMetaHarness(clock)


def test_shared_signature_validation(shared):
    body = wf.serialize(
        wf.build_message_payload("biz-1", CUSTOMER, "incoming", "Merhaba", shared.clock.now())
    )
    assert shared.provider.verify_signature(body, wf.sign(body, SECRET))
    assert not shared.provider.verify_signature(body, wf.sign(body, "wrong-secret"))
    assert not shared.provider.verify_signature(body, None)


@pytest.mark.parametrize(
    "name",
    [
        "text_message",
        "attachments",
        "story_reply",
        "story_mention",
        "echo_app",
        "echo_native",
        "reaction",
        "message_deleted",
        "unsupported",
    ],
)
def test_shared_parse_all_synthetic_webhook_fixtures(shared, name):
    (event,) = shared.provider.parse_webhook(meta_fixture("webhook_" + name))
    assert event.account_id == "biz-1" and event.customer_id == CUSTOMER
    if name == "message_deleted":
        assert event.event_type == "delete"
    elif name.startswith("echo_"):
        assert event.event_type == "echo" and event.app_id
    elif name == "reaction":
        assert event.event_type == "reaction"
    else:
        assert event.event_type == "message"
    if name in ("story_reply", "story_mention", "unsupported"):
        assert event.attachments[0]["type"] == name
    if name == "story_reply":
        assert event.attachments[0]["note"] == "story-1"
    if name == "unsupported":
        assert event.attachments[0]["note"] == "unsupported"


def test_shared_profile_and_send_and_lookup(shared):
    assert shared.provider.get_account_profile(shared.account).external_account_id == "biz-1"
    shared.customer_writes()
    since = shared.clock.now()
    first = shared.provider.send_text_message(shared.account, CUSTOMER, "first")
    shared.clock.advance(minutes=5)
    shared.provider.send_text_message(shared.account, CUSTOMER, "second")
    found = shared.provider.find_recent_outbound(shared.account, CUSTOMER, since)
    assert [v.text for v in found] == ["first", "second"]
    assert found[0].message_id == first.message_id
    assert [
        v.text
        for v in shared.provider.find_recent_outbound(
            shared.account, CUSTOMER, since + timedelta(minutes=1)
        )
    ] == ["second"]
    assert shared.provider.find_recent_outbound(shared.account, "other", since) == []


def test_shared_window_and_utf8_prevalidation(shared):
    with pytest.raises(ProviderWindowClosed):
        shared.provider.send_text_message(shared.account, CUSTOMER, "hello")
    shared.customer_writes()
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.send_text_message(shared.account, CUSTOMER, "\u00e9" * 501)
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.send_text_message(shared.account, CUSTOMER, "  ")
    shared.provider.send_text_message(shared.account, CUSTOMER, "\u00e9" * 500)
    shared.clock.advance(hours=24)
    with pytest.raises(ProviderWindowClosed):
        shared.provider.send_text_message(shared.account, CUSTOMER, "hello")


@pytest.mark.parametrize(("mode", "error"), MAPPING)
def test_shared_error_taxonomy(shared, mode, error):
    shared.customer_writes()
    shared.fail("send", mode)
    with pytest.raises(error):
        shared.provider.send_text_message(shared.account, CUSTOMER, "Merhaba")
    assert shared.provider.find_recent_outbound(shared.account, CUSTOMER, shared.clock.now()) == []


def test_shared_rate_after_and_ambiguous_send_reconciliation(shared):
    shared.customer_writes()
    shared.fail("send", "rate_limited", retry_after=77)
    with pytest.raises(ProviderRateLimited) as error:
        shared.provider.send_text_message(shared.account, CUSTOMER, "Merhaba")
    assert error.value.retry_after_s == 77
    shared.fail("send", "timeout_after_success")
    with pytest.raises(ProviderOutcomeUnknown):
        shared.provider.send_text_message(shared.account, CUSTOMER, "accepted")
    assert [
        v.text
        for v in shared.provider.find_recent_outbound(shared.account, CUSTOMER, shared.clock.now())
    ] == ["accepted"]


def test_shared_container_lifecycle_rejects_duplicate_publish(shared):
    cid = shared.container()
    assert shared.provider.get_container_status(shared.account, cid).status_code == "IN_PROGRESS"
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.publish_container(shared.account, cid)
    shared.clock.advance(seconds=CONTAINER_DELAY_S)
    assert shared.provider.get_container_status(shared.account, cid).status_code == "FINISHED"
    mid = shared.provider.publish_container(shared.account, cid)
    assert shared.provider.get_container_status(shared.account, cid).status_code == "PUBLISHED"
    assert shared.provider.get_media(shared.account, mid).media_id == mid
    assert shared.provider.get_media(shared.account, mid).permalink
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.publish_container(shared.account, cid)
    assert shared.provider.get_publishing_quota(shared.account).used == 1


def test_shared_container_expiry_and_caption_rejection(shared):
    cid = shared.container()
    shared.clock.advance(hours=24)
    assert shared.provider.get_container_status(shared.account, cid).status_code == "EXPIRED"
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.publish_container(shared.account, cid)
    with pytest.raises(ProviderInvalidRequest):
        shared.provider.create_media_container(
            shared.account, ContainerSpec("STORIES", shared.image_url(), "caption")
        )


def test_shared_unknown_publish_reconciles_without_second_publish(shared):
    cid = shared.container()
    shared.clock.advance(seconds=CONTAINER_DELAY_S)
    shared.fail("publish", "timeout_after_success")
    with pytest.raises(ProviderOutcomeUnknown):
        shared.provider.publish_container(shared.account, cid)
    assert shared.provider.get_container_status(shared.account, cid).status_code == "PUBLISHED"
    assert shared.provider.get_publishing_quota(shared.account).used == 1
