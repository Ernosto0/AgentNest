"""Decided-callbacks registry (workflows.md §D, state-machines.md §1).

A subject module (commands now; reply drafts and content later) registers what happens when
its approval is decided or expires. The callback runs in the **same transaction** as the
decision: if it raises, the whole decision rolls back and the approval stays pending, so there
are no half-states.
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.context import WorkspaceContext

# (session, clock, ctx of the decider or of the system, the approval after its transition)
DecidedCallback = Callable[[Session, Clock, WorkspaceContext, Approval], None]
# Current version of the subject, or None if it no longer exists.
VersionResolver = Callable[[Session, WorkspaceContext, uuid.UUID], int | None]
# A short status label of the subject for the approval API.
StatusResolver = Callable[[Session, WorkspaceContext, uuid.UUID], str | None]


@dataclass(frozen=True)
class SubjectHandler:
    on_decided: DecidedCallback
    current_version: VersionResolver
    status_of: StatusResolver


_REGISTRY: dict[str, SubjectHandler] = {}


def register(
    subject_type: str,
    on_decided: DecidedCallback,
    *,
    current_version: VersionResolver,
    status_of: StatusResolver,
) -> None:
    if subject_type in _REGISTRY:
        raise ValueError(f"approval subject already registered: {subject_type}")
    _REGISTRY[subject_type] = SubjectHandler(on_decided, current_version, status_of)


def get(subject_type: str) -> SubjectHandler | None:
    return _REGISTRY.get(subject_type)


@contextmanager
def callbacks_snapshot(*, clear: bool = False) -> Iterator[None]:
    """Restore the registry on exit (tests); ``clear`` starts from an empty one."""
    saved = dict(_REGISTRY)
    if clear:
        _REGISTRY.clear()
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)
