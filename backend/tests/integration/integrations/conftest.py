"""Fixtures of the integration-failure tests (workflow G): the inbox world, to send replies, and
the publishing harness, to publish posts. A test uses one of them, never both (each builds its
own workspace)."""

from tests.integration.content.conftest import app, env, make_pub, media_root, pub
from tests.integration.inbox.conftest import _send_reply_stub, inbox, provider

__all__ = [
    "_send_reply_stub",
    "app",
    "env",
    "inbox",
    "make_pub",
    "media_root",
    "provider",
    "pub",
]
