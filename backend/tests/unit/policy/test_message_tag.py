"""The Human Agent tag rule: pure boundaries and the rejection of every automated source."""

from datetime import UTC, datetime, timedelta

import pytest

from app.policy.message_tag import (
    AUTOMATED_SOURCE,
    DISABLED,
    HUMAN_AGENT_WINDOW,
    STANDARD_WINDOW,
    WINDOW_CLOSED,
    MessageTagInput,
    evaluate_message_tag,
    window_state,
)

T0 = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
MARGIN = timedelta(minutes=2)


def make(after: timedelta, **overrides: object) -> MessageTagInput:
    values: dict[str, object] = {
        "now": T0 + after,
        "last_inbound_at": T0,
        "human_agent_available": True,
        "source": "owner",
        "origin": "legacy",
        "actor_type": "user",
        "margin": MARGIN,
    }
    values.update(overrides)
    return MessageTagInput(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("after", "state"),
    [
        (timedelta(0), "open"),
        (STANDARD_WINDOW - MARGIN - timedelta(seconds=1), "open"),
        (STANDARD_WINDOW - MARGIN, "human_agent_only"),
        (STANDARD_WINDOW, "human_agent_only"),
        (STANDARD_WINDOW + timedelta(seconds=1), "human_agent_only"),
        (HUMAN_AGENT_WINDOW - MARGIN - timedelta(seconds=1), "human_agent_only"),
        (HUMAN_AGENT_WINDOW - MARGIN, "closed"),
        (HUMAN_AGENT_WINDOW + timedelta(seconds=1), "closed"),
    ],
)
def test_window_state_boundaries(after: timedelta, state: str) -> None:
    assert window_state(T0, T0 + after, human_agent_available=True, margin=MARGIN) == state


def test_without_the_capability_the_window_closes_at_24_hours() -> None:
    for after, state in [
        (STANDARD_WINDOW - MARGIN - timedelta(seconds=1), "open"),
        (STANDARD_WINDOW - MARGIN, "closed"),
        (timedelta(days=3), "closed"),
    ]:
        assert window_state(T0, T0 + after, human_agent_available=False, margin=MARGIN) == state


def test_no_customer_message_is_a_closed_window() -> None:
    assert window_state(None, T0, human_agent_available=True) == "closed"
    decision = evaluate_message_tag(make(timedelta(0), last_inbound_at=None))
    assert (decision.allowed, decision.reasons) == (False, (WINDOW_CLOSED,))


def test_inside_the_standard_window_no_tag_is_used() -> None:
    decision = evaluate_message_tag(make(timedelta(hours=3)))
    assert (decision.allowed, decision.use_tag, decision.reasons) == (True, False, ())


@pytest.mark.parametrize(
    "after",
    [
        STANDARD_WINDOW - MARGIN,
        STANDARD_WINDOW,
        timedelta(days=3),
        HUMAN_AGENT_WINDOW - MARGIN - timedelta(seconds=1),
    ],
)
def test_a_persons_reply_after_24_hours_uses_the_tag_until_7_days(after: timedelta) -> None:
    decision = evaluate_message_tag(make(after))
    assert (decision.allowed, decision.use_tag, decision.reasons) == (True, True, ())


def test_after_7_days_it_is_refused() -> None:
    decision = evaluate_message_tag(make(HUMAN_AGENT_WINDOW - MARGIN))
    assert (decision.allowed, decision.use_tag, decision.reasons) == (
        False,
        False,
        (WINDOW_CLOSED,),
    )


def test_capability_off_refuses_and_names_the_switch_for_a_tagged_draft() -> None:
    plain = evaluate_message_tag(make(timedelta(days=2), human_agent_available=False))
    assert (plain.allowed, plain.reasons) == (False, (WINDOW_CLOSED,))
    tagged = evaluate_message_tag(
        make(timedelta(days=2), human_agent_available=False, tag_requested=True)
    )
    assert (tagged.allowed, tagged.reasons) == (False, (DISABLED,))


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "ai"},
        {"source": "approved_answer"},  # also what a follow-up draft is stored as
        {"origin": "agent"},
        {"actor_type": "system"},
        {"actor_type": "agent"},
        {"is_agent_action": True},
        {"is_follow_up": True},
    ],
)
@pytest.mark.parametrize("after", [timedelta(days=2), timedelta(hours=26), timedelta(days=6)])
def test_every_automated_source_is_rejected_after_the_standard_window(
    overrides: dict[str, object], after: timedelta
) -> None:
    decision = evaluate_message_tag(make(after, **overrides))
    assert (decision.allowed, decision.use_tag, decision.reasons) == (
        False,
        False,
        (AUTOMATED_SOURCE,),
    )


@pytest.mark.parametrize(
    "overrides", [{"source": "ai"}, {"is_follow_up": True}, {"origin": "agent"}]
)
def test_an_automated_draft_holding_the_tag_is_rejected_even_inside_the_window(
    overrides: dict[str, object],
) -> None:
    decision = evaluate_message_tag(make(timedelta(hours=1), tag_requested=True, **overrides))
    assert (decision.allowed, decision.reasons) == (False, (AUTOMATED_SOURCE,))
    # An automated draft that never asked for the tag is simply a normal in-window message.
    assert evaluate_message_tag(make(timedelta(hours=1), **overrides)).allowed is True
