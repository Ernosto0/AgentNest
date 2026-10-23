"""Encrypted persisted credentials reach real adapter through ledger executor registry."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.security import TokenKeyRing, account_token_aad
from app.integrations.instagram import registry
from app.integrations.instagram.meta import MetaInstagramProvider
from app.operations.health_check import run_health_check
from app.operations.reconcile import reconcile_send
from app.operations.send import execute_send_reply
from tests.helpers.publishing import GuardedFactory
from tests.integration.inbox.conftest import InboxEnv

TOKEN = "synthetic-executor-token"
KEYS = "k1:a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


def configure(inbox: InboxEnv):
    cfg = inbox.settings.model_copy(
        update={
            "instagram_enabled_providers": "meta",
            "token_encryption_keys": SecretStr(KEYS),
            "token_encryption_active_key_id": "k1",
        }
    )
    account = inbox.account
    account.provider_kind = "meta"
    account.token_ciphertext, account.token_key_id = TokenKeyRing(KEYS, "k1").encrypt(
        TOKEN, aad=account_token_aad(account.workspace_id, account.id)
    )
    inbox.session.commit()
    return cfg


@pytest.mark.parametrize("malformed_send", [False, True])
def test_registry_send_and_reconcile_decrypt_only_outside_transactions(
    inbox: InboxEnv, monkeypatch: pytest.MonkeyPatch, malformed_send: bool
) -> None:
    inbox.seed_facts()
    draft = inbox.ask()
    assert inbox.decide(draft).status_code == 200
    cfg = configure(inbox)
    guard = GuardedFactory(inbox.factory)
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert guard.open_transactions() == 0
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["message"]["text"] == draft.text
            return httpx.Response(
                200, json={} if malformed_send else {"message_id": "meta-delivered"}
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "conversation",
                        "messages": {
                            "data": [
                                {
                                    "id": "meta-delivered",
                                    "from": {"id": inbox.account.external_account_id},
                                    "to": {"data": [{"id": "cust-1"}]},
                                    "message": draft.text,
                                    "created_time": inbox.clock.now().isoformat(),
                                }
                            ]
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(
        registry,
        "MetaInstagramProvider",
        lambda clock, secret, version: MetaInstagramProvider(
            clock, secret, version, transport=httpx.MockTransport(handle)
        ),
    )
    result = execute_send_reply(guard, inbox.clock, cfg, inbox.env.workspace.id, draft.id)
    if malformed_send:
        assert result.kind == "unknown"
        op = inbox.operation(draft)
        assert op and op.status == "outcome_unknown"
        assert reconcile_send(guard, inbox.clock, cfg, inbox.env.workspace.id, op.id) == "sent"
    else:
        assert result.kind == "sent"
    assert len([r for r in calls if r.method == "POST"]) == 1
    assert inbox.refreshed(draft).status == "sent"
    assert inbox.operation(draft).status == "succeeded"


@pytest.mark.parametrize("tampered", [False, True])
def test_health_registry_read_and_decryption_failure(
    inbox: InboxEnv, monkeypatch: pytest.MonkeyPatch, tampered: bool
) -> None:
    cfg = configure(inbox)
    inbox.account.status = "degraded"
    if tampered:
        inbox.account.token_ciphertext = b"tampered"
    inbox.session.commit()
    guard = GuardedFactory(inbox.factory)
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert guard.open_transactions() == 0
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        calls.append(request)
        return httpx.Response(
            200, json={"user_id": inbox.account.external_account_id, "username": "synthetic"}
        )

    monkeypatch.setattr(
        registry,
        "MetaInstagramProvider",
        lambda clock, secret, version: MetaInstagramProvider(
            clock, secret, version, transport=httpx.MockTransport(handle)
        ),
    )
    result = run_health_check(guard, inbox.clock, cfg, inbox.env.workspace.id, inbox.account.id)
    assert result == ("needs_reauth" if tampered else "recovered")
    assert len(calls) == (0 if tampered else 1)
