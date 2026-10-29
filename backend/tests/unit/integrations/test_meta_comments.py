"""Synthetic assumptions only; none of these fixtures records live Meta behavior."""

import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.errors import (
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
)
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.meta_comments import SyntheticMetaCommentProvider
from app.integrations.instagram.oauth import COMMENT_CAPABILITIES, compute_capabilities

FIXTURE = Path(__file__).parents[2] / "contract/fixtures/meta/comments_synthetic_v1.json"


class API:
    def __init__(self, clock):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.calls = []
        self.mutation = {"id": "reply-1"}
        self.status = 200
        self.failure = None
        self.account = AccountRef(uuid.uuid4(), uuid.uuid4(), "business-1", lambda: "secret-token")
        self.provider = SyntheticMetaCommentProvider(
            clock, "v25.0", transport=httpx.MockTransport(self.handle)
        )

    def handle(self, request):
        self.calls.append(request)
        assert request.url.host == "graph.instagram.com"
        assert request.headers["Authorization"] == "Bearer secret-token"
        if request.method != "GET":
            if self.failure:
                raise self.failure("secret-token", request=request)
            return httpx.Response(self.status, json=self.mutation, headers={"Retry-After": "30"})
        if request.url.path.endswith(("/media-1", "/foreign-media")):
            return httpx.Response(200, json=self.data["media"])
        if request.url.path.endswith("/media-1/comments"):
            return httpx.Response(
                200, json=self.data["second_page" if request.url.params.get("after") else "page"]
            )
        return httpx.Response(200, json=self.data["comment"])


def test_scaffold_cannot_use_real_transport(clock):
    with pytest.raises(ValueError, match="exact MockTransport"):
        SyntheticMetaCommentProvider(clock, "v25.0", transport=httpx.HTTPTransport())


def test_production_default_blocks_all_comment_paths_without_network(clock):
    def forbidden(request):
        pytest.fail("disabled production capability made an HTTP request")

    provider = MetaInstagramProvider(clock, "", "v25.0", transport=httpx.MockTransport(forbidden))
    account = API(clock).account
    for call in (
        lambda: provider.read_comments(account, "media-1"),
        lambda: provider.read_comment(account, "comment-1"),
        lambda: provider.perform_comment_effect(account, "comment-1", "reply", "Hi", "op"),
        lambda: provider.send_private_reply(account, "comment-1", "Hi", "op"),
        lambda: provider.find_comment_effect(account, "op"),
        lambda: provider.find_private_reply(account, "op"),
    ):
        with pytest.raises(ProviderInvalidRequest, match="NOT_VERIFIED"):
            call()
    caps = compute_capabilities(["instagram_business_manage_comments"], True)
    assert all(caps[key] is False for key in COMMENT_CAPABILITIES)


def test_pagination_never_follows_remote_next_host(clock):
    api = API(clock)
    values = api.provider.read_comments(api.account, "media-1")
    assert [value.id for value in values] == ["comment-1", "comment-2"]
    assert api.calls[-1].url.params["after"] == "cursor-2"
    assert all(call.url.host == "graph.instagram.com" for call in api.calls)


@pytest.mark.parametrize("bad", ["owner", "media", "target"])
def test_scoped_source_checks_precede_mutation(clock, bad):
    api = API(clock)
    if bad == "owner":
        api.data["media"]["owner"]["id"] = "foreign-account"
    elif bad == "media":
        api.data["comment"]["media"]["id"] = "foreign-media"
    else:
        api.data["comment"]["id"] = "foreign-comment"
    with pytest.raises(ProviderInvalidRequest):
        api.provider.perform_comment_effect(api.account, "comment-1", "reply", "Hi", "op")
    assert all(call.method == "GET" for call in api.calls)


@pytest.mark.parametrize("effect", ["reply", "hide", "unhide", "delete"])
def test_provisional_mutation_shapes_have_no_fabricated_readback(clock, effect):
    api = API(clock)
    api.mutation = {"id": "reply-1"} if effect == "reply" else {"success": True}
    result = api.provider.perform_comment_effect(
        api.account, "comment-1", effect, "Hi" if effect == "reply" else None, "local-operation"
    )
    call = api.calls[-1]
    assert call.method == ("DELETE" if effect == "delete" else "POST")
    assert result.state is None
    assert api.provider.find_comment_effect(api.account, "local-operation") is None
    assert api.provider.find_private_reply(api.account, "local-operation") is None


@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError]
)
def test_uncertain_effect_never_retries_or_exposes_token(clock, failure):
    api = API(clock)
    api.failure = failure
    with pytest.raises(ProviderOutcomeUnknown) as caught:
        api.provider.perform_comment_effect(api.account, "comment-1", "reply", "Hi", "op")
    assert "secret-token" not in str(caught.value)
    assert len([call for call in api.calls if call.method == "POST"]) == 1


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, {}, ProviderOutcomeUnknown),
        (200, {"success": True}, ProviderOutcomeUnknown),
        (500, {"error": {"code": 4}}, ProviderOutcomeUnknown),
        (400, {"error": {"is_transient": True}}, ProviderOutcomeUnknown),
        (429, {"error": {"code": 4}}, ProviderRateLimited),
        (403, {"error": {"code": 10}}, ProviderPermissionError),
    ],
)
def test_mutation_errors_are_typed(clock, status, body, expected):
    api = API(clock)
    api.status, api.mutation = status, body
    with pytest.raises(expected):
        api.provider.perform_comment_effect(api.account, "comment-1", "reply", "Hi", "op")


def test_connect_failure_is_safe_but_not_automatically_retried(clock):
    api = API(clock)
    api.failure = httpx.ConnectTimeout
    with pytest.raises(ProviderTransientError):
        api.provider.perform_comment_effect(api.account, "comment-1", "reply", "Hi", "op")
    assert len([call for call in api.calls if call.method == "POST"]) == 1


@pytest.mark.parametrize("days", [7, 8, -1])
def test_private_reply_expiry_and_future_source_prevent_dispatch(clock, days):
    api = API(clock)
    api.data["comment"]["timestamp"] = (clock.now() - timedelta(days=days)).isoformat()
    with pytest.raises(ProviderInvalidRequest, match="EXPIRED"):
        api.provider.send_private_reply(api.account, "comment-1", "Hi", "op")
    assert all(call.method == "GET" for call in api.calls)


def test_private_reply_response_identity_is_optional_and_not_guessed(clock):
    api = API(clock)
    api.data["comment"]["timestamp"] = clock.now().isoformat()
    api.mutation = {"message_id": "private-1"}
    value = api.provider.send_private_reply(api.account, "comment-1", "Hi", "op")
    assert value.reply_id == "private-1" and value.recipient_id is None
    assert json.loads(api.calls[-1].content)["recipient"] == {"comment_id": "comment-1"}


@pytest.mark.parametrize("text", ["", " ", "ç" * 501])
def test_bad_text_has_no_network_request(clock, text):
    api = API(clock)
    with pytest.raises(ProviderInvalidRequest):
        api.provider.send_private_reply(api.account, "comment-1", text, "op")
    assert api.calls == []


def test_pagination_loop_is_incomplete_not_a_partial_success(clock):
    api = API(clock)
    api.data["second_page"] = api.data["page"]
    with pytest.raises(ProviderTransientError, match="INCOMPLETE"):
        api.provider.read_comments(api.account, "media-1")


@pytest.mark.parametrize("data", [{}, {"data": "bad"}, {"data": [{}]}])
def test_malformed_read_never_returns_partial_comments(clock, data):
    api = API(clock)
    api.data["page"] = data
    with pytest.raises(ProviderTransientError):
        api.provider.read_comments(api.account, "media-1")


@pytest.mark.parametrize("body", [{}, {"success": False}, {"success": "true"}])
def test_malformed_moderation_acknowledgement_is_unknown(clock, body):
    api = API(clock)
    api.mutation = body
    with pytest.raises(ProviderOutcomeUnknown):
        api.provider.perform_comment_effect(api.account, "comment-1", "hide", None, "op")


def test_private_reply_timeout_has_no_retry_or_identity_guess(clock):
    api = API(clock)
    api.data["comment"]["timestamp"] = clock.now().isoformat()
    api.failure = httpx.ReadTimeout
    with pytest.raises(ProviderOutcomeUnknown):
        api.provider.send_private_reply(api.account, "comment-1", "Hi", "op")
    assert len([call for call in api.calls if call.method == "POST"]) == 1
    assert api.provider.find_private_reply(api.account, "op") is None
