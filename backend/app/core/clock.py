"""Injected time source. All business logic reads time from a ``Clock`` (INV-19)."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant, UTC, timezone-aware."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic clock for tests; moves only when ``advance`` is called."""

    def __init__(self, start: datetime | None = None) -> None:
        start = start or datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        if start.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware start")
        self._now = start.astimezone(UTC)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, delta: timedelta | None = None, **kwargs: float) -> datetime:
        """Advance by a ``timedelta`` or by keyword arguments, e.g. ``advance(minutes=5)``."""
        step = (delta or timedelta()) + timedelta(**kwargs)
        if step < timedelta():
            raise ValueError("FrozenClock cannot move backwards")
        with self._lock:
            self._now += step
            return self._now
