"""Optional live WhatsApp Cloud API probe harness (never run in CI, skipped without credentials).

Required, all explicit: WHATSAPP_LIVE_ACCESS_TOKEN, WHATSAPP_LIVE_PHONE_NUMBER_ID and
WHATSAPP_LIVE_TO (the wa_id of a test phone that wrote to the business number within the last
24 hours, because the interactive probe is a session message). Nothing here reads the app's own
WHATSAPP_* settings, so a developer with production credentials in ``.env`` cannot send by accident.

The probes send one fixed ping and one interactive message whose buttons carry **probe ids, not
action tokens**: tapping them decides nothing (the webhook answers "this button is not valid").
They record what Meta really accepts so the "pending live" items in the Track A summary can be
closed by a person; they never read a webhook and never print provider bodies or credentials.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest
from pydantic import SecretStr

from app.integrations.channels.whatsapp.client import WhatsAppClient

pytestmark = pytest.mark.whatsapp_live


def _probe[T](call: Callable[[], T]) -> T:
    """Suppress raw exceptions that could carry credentials or provider bodies."""
    try:
        return call()
    except Exception:  # noqa: S110 - raw exceptions may contain credentials; never log them.
        pass
    pytest.fail("Live WhatsApp probe failed; check the number, token and window.", pytrace=False)


def _check(condition: bool) -> None:
    if not condition:
        pytest.fail("Live WhatsApp probe contract expectation failed.", pytrace=False)


@pytest.fixture
def live_inputs() -> tuple[str, str, str]:
    token = os.environ.get("WHATSAPP_LIVE_ACCESS_TOKEN", "").strip()
    number_id = os.environ.get("WHATSAPP_LIVE_PHONE_NUMBER_ID", "").strip()
    to = os.environ.get("WHATSAPP_LIVE_TO", "").strip()
    if not token or not number_id or not to:
        pytest.skip(
            "Live WhatsApp probes require WHATSAPP_LIVE_ACCESS_TOKEN, "
            "WHATSAPP_LIVE_PHONE_NUMBER_ID and WHATSAPP_LIVE_TO."
        )
    return token, number_id, to


@pytest.fixture
def live_client(live_inputs: tuple[str, str, str]) -> WhatsAppClient:
    token, number_id, _ = live_inputs
    return WhatsAppClient(access_token=SecretStr(token), phone_number_id=number_id)


def test_live_whatsapp_session_text_ping(
    live_client: WhatsAppClient, live_inputs: tuple[str, str, str]
) -> None:
    """A free-form message inside the 24-hour window is accepted and returns a message id."""
    result = _probe(lambda: live_client.send_text(live_inputs[2], "[Pivoris] Live probe: OK"))
    _check(result.message_id.startswith("wamid."))


def test_live_whatsapp_interactive_buttons_with_probe_ids(
    live_client: WhatsAppClient, live_inputs: tuple[str, str, str]
) -> None:
    """Two reply buttons are accepted; their ids are probe ids that decide nothing if tapped."""
    result = _probe(
        lambda: live_client.send_interactive_buttons(
            live_inputs[2],
            "[Pivoris] Live probe: these buttons do nothing.",
            [("probe:approve", "Approve"), ("probe:reject", "Reject")],
        )
    )
    _check(result.message_id.startswith("wamid."))
