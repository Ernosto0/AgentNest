"""Registry-built Meta publishing and reconciliation retain lazy encrypted snapshots."""

import httpx
import pytest
from pydantic import SecretStr

from app.core.security import TokenKeyRing, account_token_aad
from app.integrations.instagram import registry
from app.integrations.instagram.meta import MetaInstagramProvider
from app.operations import publish
from tests.helpers.publishing import Publishing

TOKEN = "synthetic-publishing-token"
KEYS = "k1:a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


@pytest.mark.parametrize("ambiguous", [False, True])
def test_registry_decrypts_for_quota_create_poll_publish_media_and_reconcile(
    pub: Publishing, monkeypatch: pytest.MonkeyPatch, ambiguous: bool
) -> None:
    item = pub.scheduled()
    account = pub.account
    account.provider_kind = "meta"
    account.token_ciphertext, account.token_key_id = TokenKeyRing(KEYS, "k1").encrypt(
        TOKEN, aad=account_token_aad(account.workspace_id, account.id)
    )
    pub.session.commit()
    cfg = pub.settings.model_copy(
        update={
            "instagram_enabled_providers": "meta",
            "token_encryption_keys": SecretStr(KEYS),
            "token_encryption_active_key_id": "k1",
        }
    )
    requests = []
    published = False

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal published
        assert pub.factory.open_transactions() == 0
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        requests.append(request)
        path = request.url.path.split("/")[-1]
        if path == "content_publishing_limit":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"quota_usage": 0, "config": {"quota_total": 50, "quota_duration": 86400}}
                    ]
                },
            )
        if path == "media":
            return httpx.Response(200, json={"id": "container-meta"})
        if path == "container-meta":
            return httpx.Response(
                200, json={"id": path, "status_code": "PUBLISHED" if published else "FINISHED"}
            )
        if path == "media_publish":
            published = True
            return httpx.Response(200, json={} if ambiguous else {"id": "media-meta"})
        assert path == "media-meta"
        return httpx.Response(
            200,
            json={
                "id": "media-meta",
                "permalink": "https://www.instagram.com/p/synthetic/",
                "timestamp": pub.clock.now().isoformat(),
            },
        )

    class Storage:
        def public_fetch_url(self, *args):
            assert pub.factory.open_transactions() == 0
            return "https://example.test/synthetic-presigned.jpg"

    monkeypatch.setattr(publish, "get_media_storage", lambda *args: Storage())
    monkeypatch.setattr(
        registry,
        "MetaInstagramProvider",
        lambda clock, secret, version: MetaInstagramProvider(
            clock, secret, version, transport=httpx.MockTransport(handle)
        ),
    )
    result = publish.execute_publish(
        pub.factory, pub.clock, cfg, pub.workspace.id, item.id, item.version
    )
    if ambiguous:
        assert result.kind == "unknown"
        operation = pub.operation(item)
        assert operation
        result = publish.reconcile_publish(
            pub.factory, pub.clock, cfg, pub.workspace.id, operation.id
        )
    assert result.kind == "published"
    assert pub.reload(item).status == "published"
    assert len([r for r in requests if r.url.path.endswith("/media_publish")]) == 1
    if ambiguous:
        assert pub.reload(item).external_permalink is None
    else:
        assert pub.reload(item).external_permalink == "https://www.instagram.com/p/synthetic/"
