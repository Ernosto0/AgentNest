"""The 24-hour customer-service window: a pure, deterministic send-mode decision (ADR-027).

A message from the owner to the business number opens a 24-hour window (every new message resets
it). Inside it a plain *session* message may be sent; outside it only an approved *template*.

The decision uses only two inputs, the owner's last inbound time (stored on the channel link by
the webhook) and the injected ``Clock``. It keeps a safety margin: the stored time is when we
processed the webhook (or Meta's own timestamp when that is earlier), and Meta may count the
window slightly differently, so a send in the last ``SAFETY_MARGIN`` of the window uses a template
rather than risk a rejected session message.

Boundaries (``age = now - last_inbound_at``): ``age < 24h - margin`` is **session**;
``age >= 24h - margin`` is **template**; no inbound time, or one in the future, is **template**.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

WINDOW = timedelta(hours=24)
SAFETY_MARGIN = timedelta(minutes=5)

SendMode = Literal["session", "template"]


def choose_send_mode(last_inbound_at: datetime | None, now: datetime) -> SendMode:
    if last_inbound_at is None:
        return "template"
    age = now - last_inbound_at
    if age < timedelta(0):
        return "template"  # a future timestamp is not evidence of an open window
    return "session" if age < WINDOW - SAFETY_MARGIN else "template"
