"""Real comment contracts exercised only with signed fixtures and MockTransport."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from app.comments.codec import CommentEvent
from app.comments.private_reply_rules import refusal
from app.core.config import Settings
from app.inbox.ingest import dedup_key
from app.integrations.instagram.base import META_PRIVATE_REPLY_WINDOW
from app.integrations.instagram.errors import ProviderInvalidRequest, ProviderOutcomeUnknown
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.oauth import (
    COMMENTS_SCOPE,
    SCOPES,
    build_authorize_url,
    compute_capabilities,
)
from app.integrations.instagram.webhook_format import WebhookCodec
from tests.unit.integrations.test_meta_comments import API


def payload(clock):
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "business",
                "time": int(clock.now().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment",
                            "from": {"id": "customer", "username": "never-store"},
                            "text": "price?",
                            "media": {"id": "media", "media_product_type": "FEED"},
                        },
                    }
                ],
            }
        ],
    }


def test_real_codec_and_dedup(clock):
    wire = payload(clock)
    codec = WebhookCodec("secret", live_comments=True)
    events = codec.parse_webhook(wire)
    assert len(events) == 1 and events[0].event_type == "comment"
    event = CommentEvent.model_validate(events[0].raw_item)
    assert event.root_id == "comment" and event.author_id == "customer" and event.media_verified
    assert "never-store" not in str(events)
    wire["entry"][0]["time"] += 3
    assert dedup_key(codec.parse_webhook(wire)[0]) == dedup_key(events[0])
    wire["entry"][0]["changes"][0]["value"]["parent_id"] = "parent"
    assert CommentEvent.model_validate(codec.parse_webhook(wire)[0].raw_item).root_id == "parent"
    assert WebhookCodec("secret").parse_webhook(wire)[0].event_type == "other"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"id": "x"},
        {"id": "x", "media": []},
        {"id": "x", "media": {"id": "m"}, "text": []},
    ],
)
def test_malformed_comments_dropped(clock, bad):
    wire = payload(clock)
    wire["entry"][0]["changes"][0]["value"] = bad
    assert WebhookCodec("secret", live_comments=True).parse_webhook(wire) == []


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"comment_used": True}, "PRIVATE_REPLY_COMMENT_ALREADY_USED"),
        ({"author_id": None}, "PRIVATE_REPLY_COMMENTER_UNKNOWN"),
        ({"parent_id": "parent"}, "PRIVATE_REPLY_NOT_TOP_LEVEL"),
        ({"commenter_used": True}, "PRIVATE_REPLY_COMMENTER_LIMIT"),
        ({"posted_at": None}, "PRIVATE_REPLY_WINDOW_EXPIRED"),
    ],
)
def test_refusal_codes(clock, update, code):
    args = {"now": clock.now(), "posted_at": clock.now(), "author_id": "person", "parent_id": None}
    assert refusal(**{**args, **update}) == code


def test_window_boundary_margin_and_relaxed_scope(clock):
    posted = clock.now()
    args = {"posted_at": posted, "author_id": "person", "parent_id": None}
    clock.advance(META_PRIVATE_REPLY_WINDOW - timedelta(microseconds=1))
    assert refusal(now=clock.now(), **args) is None
    clock.advance(timedelta(microseconds=1))
    assert refusal(now=clock.now(), **args) == "PRIVATE_REPLY_WINDOW_EXPIRED"
    assert timedelta(days=7, minutes=-10) == META_PRIVATE_REPLY_WINDOW
    assert refusal(now=posted, **args, commenter_used=True, limit_scope="comment") is None


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("granted", [False, True])
def test_capabilities_and_scope_switch(settings, enabled, granted):
    c = compute_capabilities([COMMENTS_SCOPE] if granted else [], True, enabled)
    assert c["comment_read"] is (enabled and granted)
    assert c["comment_private_reply"] is (enabled and granted)
    assert not c["comment_reply"] and not c["comment_moderate"]
    cfg = settings.model_copy(update={"meta_request_comment_scope": enabled})
    scopes = parse_qs(urlsplit(build_authorize_url(cfg, "state")).query)["scope"][0].split(",")
    assert scopes == list(SCOPES if enabled else SCOPES[:-1])


def test_invalid_limit_setting():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, comment_private_reply_limit_scope="invalid")


def real_api(clock):
    api = API(clock)
    api.provider = MetaInstagramProvider(
        clock, "", "v25.0", transport=httpx.MockTransport(api.handle)
    )
    api.data["comment"]["timestamp"] = clock.now().isoformat()
    api.mutation = {"message_id": "reply", "recipient_id": "recipient"}
    return api


def test_real_private_transport_and_no_readback(clock):
    api = real_api(clock)
    result = api.provider.send_private_reply(api.account, "comment-1", "Hello", "op")
    assert result.reply_id == "reply" and result.recipient_id == "recipient"
    assert api.calls[-1].url.path.endswith("/business-1/messages")
    assert api.provider.find_private_reply(api.account, "op") is None


@pytest.mark.parametrize("mode", ["owner", "expired", "timeout", "4xx"])
def test_transport_refusals_are_sanitized(clock, mode, caplog):
    api = real_api(clock)
    if mode == "owner":
        api.data["media"]["owner"]["id"] = "foreign"
    elif mode == "expired":
        api.data["comment"]["timestamp"] = (clock.now() - META_PRIVATE_REPLY_WINDOW).isoformat()
    elif mode == "timeout":
        api.failure = httpx.ReadTimeout
    else:
        api.status, api.mutation = 400, {"error": {"code": 100, "message": "secret-token"}}
    with pytest.raises(
        ProviderOutcomeUnknown if mode == "timeout" else ProviderInvalidRequest
    ) as error:
        api.provider.send_private_reply(api.account, "comment-1", "Hello", "op")
    assert "secret-token" not in str(error.value) + caplog.text
    if mode in {"owner", "expired"}:
        assert all(call.method == "GET" for call in api.calls)


@pytest.mark.parametrize("simulated", [False, True])
@pytest.mark.parametrize("state", ["unverified", "verified_provider", "verified_synthetic"])
def test_provider_specific_ownership(simulated, state):
    from app.comments.models import PublicMedia
    from app.comments.ownership import media_ownership_ok

    media = PublicMedia(ownership_state=state)
    expected = "verified_synthetic" if simulated else "verified_provider"
    assert media_ownership_ok(media, simulated) is (state == expected)


@pytest.mark.parametrize("length", [0, 1002])
def test_real_private_text_limits_before_network(clock, length):
    api = real_api(clock)
    with pytest.raises(ProviderInvalidRequest, match="INVALID_COMMENT_REPLY"):
        api.provider.send_private_reply(api.account, "comment-1", "ü" * (length // 2), "op")
    assert api.calls == []


def test_malformed_timestamp_drops_without_other_event(clock):
    wire = payload(clock)
    wire["entry"][0]["time"] = "nan"
    assert WebhookCodec("secret", live_comments=True).parse_webhook(wire) == []
