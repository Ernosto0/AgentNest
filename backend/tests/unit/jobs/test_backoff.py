import random

import pytest

from app.jobs.queue import DEFAULT_BACKOFF_SECONDS, backoff_seconds
from app.jobs.worker import DETAIL_MAX_CHARS, sanitize_detail


class FixedJitter(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value

    def uniform(self, a: float, b: float) -> float:
        return self.value


def test_default_schedule_is_10s_1m_5m_15m_1h() -> None:
    assert DEFAULT_BACKOFF_SECONDS == (10, 60, 300, 900, 3600)
    rng = FixedJitter(0.0)
    assert [backoff_seconds(n, rng=rng) for n in range(1, 6)] == [10, 60, 300, 900, 3600]


def test_attempts_beyond_the_schedule_use_the_last_step() -> None:
    assert backoff_seconds(6, rng=FixedJitter(0.0)) == 3600
    assert backoff_seconds(50, rng=FixedJitter(0.0)) == 3600


def test_jitter_is_plus_or_minus_20_percent() -> None:
    assert backoff_seconds(2, rng=FixedJitter(0.2)) == pytest.approx(72)
    assert backoff_seconds(2, rng=FixedJitter(-0.2)) == pytest.approx(48)
    samples = [backoff_seconds(3) for _ in range(500)]
    assert all(240 <= s <= 360 for s in samples)
    assert max(samples) - min(samples) > 30  # it really is random


def test_custom_schedule_overrides_the_default() -> None:
    assert backoff_seconds(1, schedule=(120, 600), rng=FixedJitter(0.0)) == 120
    assert backoff_seconds(9, schedule=(120, 600), rng=FixedJitter(0.0)) == 600


def test_attempt_numbers_below_one_are_treated_as_the_first() -> None:
    assert backoff_seconds(0, rng=FixedJitter(0.0)) == 10


def test_sanitize_detail_redacts_secrets_and_truncates() -> None:
    redacted = sanitize_detail("call failed: Authorization: abc123 token=xyz api_key=k")
    assert redacted is not None
    assert "abc123" not in redacted and "xyz" not in redacted and "=k" not in redacted
    assert "[REDACTED]" in redacted
    long = sanitize_detail("e" * 5000)
    assert long is not None and len(long) == DETAIL_MAX_CHARS
    assert sanitize_detail(None) is None
    assert sanitize_detail("") is None
