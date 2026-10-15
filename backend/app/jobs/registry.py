"""Job handler registry: ``@job_handler("type", PayloadModel, max_attempts=3, timeout=...)``.

A handler receives a ``JobContext``. It re-reads and re-checks domain state, manages its own
transactions via ``ctx.session_factory`` and never holds a transaction open across an
external call (background-jobs.md §5).
"""

import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock

DEFAULT_MAX_ATTEMPTS = 3


@dataclass
class JobContext:
    """Everything a handler needs. ``payload`` is already validated."""

    job_id: uuid.UUID
    job_type: str
    workspace_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    payload: BaseModel
    attempt: int  # 1-based number of this execution
    max_attempts: int
    session_factory: sessionmaker[Session]
    clock: Clock
    _heartbeat: Callable[[], None]

    def heartbeat(self) -> None:
        """Extend the lease. Raises ``JobLeaseLost`` if another worker has taken the job."""
        self._heartbeat()


HandlerFunc = Callable[[JobContext], None]
OnDeadHook = Callable[[JobContext, str], None]  # (context, error_code)


@dataclass(frozen=True)
class RegisteredHandler:
    job_type: str
    payload_model: type[BaseModel]
    func: HandlerFunc
    max_attempts: int
    # Lease to hold while the handler runs, if longer than JOB_LEASE_SECONDS.
    timeout_seconds: float | None
    on_dead: OnDeadHook | None
    backoff_seconds: Sequence[float] | None  # overrides the default schedule


class JobLeaseLost(Exception):
    """The job's lease expired and another worker claimed it; stop without finalising."""


_REGISTRY: dict[str, RegisteredHandler] = {}


def job_handler(
    job_type: str,
    payload_model: type[BaseModel],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: float | None = None,
    on_dead: OnDeadHook | None = None,
    backoff: Sequence[float] | None = None,
) -> Callable[[HandlerFunc], HandlerFunc]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(func: HandlerFunc) -> HandlerFunc:
        if job_type in _REGISTRY:
            raise ValueError(f"job type already registered: {job_type}")
        _REGISTRY[job_type] = RegisteredHandler(
            job_type=job_type,
            payload_model=payload_model,
            func=func,
            max_attempts=max_attempts,
            timeout_seconds=timeout,
            on_dead=on_dead,
            backoff_seconds=backoff,
        )
        return func

    return decorator


def get_handler(job_type: str) -> RegisteredHandler | None:
    return _REGISTRY.get(job_type)


def registered_job_types() -> list[str]:
    return sorted(_REGISTRY)


@contextmanager
def registry_snapshot() -> Iterator[None]:
    """Restore the registry on exit, so tests can register throw-away handlers."""
    saved: dict[str, Any] = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)
