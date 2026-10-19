"""Echo matching hook (workflows.md §C).

An echo is a message the business sent. If it is the echo of a send we made (or are checking),
the send machinery must claim it; otherwise it was typed in the native Instagram app. The
operations module registers a matcher at startup, so inbox needs no import of operations
(component-design.md §3, rule 6).
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext


@dataclass(frozen=True)
class Echo:
    social_account_id: uuid.UUID
    customer_id: str
    mid: str | None
    text: str | None
    provider_timestamp: datetime


# Returns True when the echo belongs to one of our own sends and has been handled.
EchoMatcher = Callable[[Session, Clock, WorkspaceContext, Echo], bool]

_MATCHERS: list[EchoMatcher] = []


def register_matcher(matcher: EchoMatcher) -> None:
    if matcher not in _MATCHERS:
        _MATCHERS.append(matcher)


def claimed_by_a_send(session: Session, clock: Clock, ctx: WorkspaceContext, echo: Echo) -> bool:
    return any(matcher(session, clock, ctx, echo) for matcher in _MATCHERS)


@contextmanager
def matchers_snapshot(*, clear: bool = False) -> Iterator[None]:
    """Restore the registry on exit (tests)."""
    saved = list(_MATCHERS)
    if clear:
        _MATCHERS.clear()
    try:
        yield
    finally:
        _MATCHERS[:] = saved
