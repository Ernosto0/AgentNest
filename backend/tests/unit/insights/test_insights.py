"""Unit tests for Instagram Insights provider, service, and summaries."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.core.clock import FrozenClock
from app.insights import service
from app.insights.models import AccountInsightDaily
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SocialAccount


def test_mock_provider_returns_deterministic_insights() -> None:
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    provider = MockInstagramProvider(
        session_factory=lambda: None,  # type: ignore[return-value]
        clock=FrozenClock(now),
        app_secret="test_secret",
    )
    ref = AccountRef(
        social_account_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        external_account_id="17841400000000001",
    )

    metrics = provider.get_account_insights(
        ref,
        ["reach", "views", "total_interactions", "follower_count"],
        since=now - timedelta(days=2),
        until=now,
    )
    assert len(metrics) > 0
    metrics_by_name = {m.metric: m.value for m in metrics}
    assert "reach" in metrics_by_name
    assert "views" in metrics_by_name
    assert metrics_by_name["reach"] > 0
    assert metrics_by_name["views"] >= metrics_by_name["reach"]

    # Media insights
    media_metrics = provider.get_media_insights(ref, "media_123", "feed_image")
    assert media_metrics.metrics["reach"] > 0
    assert media_metrics.metrics["views"] >= media_metrics.metrics["reach"]

    story_metrics = provider.get_media_insights(ref, "story_456", "story_image")
    assert story_metrics.metrics["reach"] > 0
    assert "navigation" in story_metrics.metrics

    # Audience
    audience = provider.get_audience(ref)
    assert audience.online_followers is not None
    assert len(audience.online_followers) == 24
    assert audience.demographics is not None


def test_get_summary_not_granted_status() -> None:
    workspace_id = uuid.uuid4()
    account_id = uuid.uuid4()

    # Meta account without the insights scope
    account = SocialAccount(
        id=account_id,
        workspace_id=workspace_id,
        provider_kind="meta",
        external_account_id="17841400000000002",
        username="test_meta",
        status="connected",
        granted_scopes=["instagram_business_basic"],
    )

    session = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.one_or_none.return_value = account
    session.scalars.return_value = mock_scalars

    summary = service.get_summary(session, workspace_id, account_id)
    assert summary.status == "not_granted"
    assert summary.reach == 0
    assert summary.views == 0


def test_get_summary_with_records_computes_aggregates_and_deltas() -> None:
    workspace_id = uuid.uuid4()
    account_id = uuid.uuid4()

    account = SocialAccount(
        id=account_id,
        workspace_id=workspace_id,
        provider_kind="mock",
        external_account_id="17841400000000001",
        username="test_mock",
        status="connected",
        granted_scopes=[],
    )

    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    today = now.date()

    # Current period rows (last 7 days: Nov 4 to Nov 10)
    current_reach = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today,
        metric="reach",
        value=500,
        fetched_at=now,
    )
    current_views = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today,
        metric="views",
        value=800,
        fetched_at=now,
    )
    current_interactions = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today,
        metric="total_interactions",
        value=50,
        fetched_at=now,
    )

    # Previous period rows
    prev_reach = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today - timedelta(days=8),
        metric="reach",
        value=400,
        fetched_at=now,
    )
    prev_views = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today - timedelta(days=8),
        metric="views",
        value=400,
        fetched_at=now,
    )
    prev_interactions = AccountInsightDaily(
        workspace_id=workspace_id,
        social_account_id=account_id,
        local_date=today - timedelta(days=8),
        metric="total_interactions",
        value=25,
        fetched_at=now,
    )

    session = MagicMock()
    account_result = MagicMock()
    account_result.one_or_none.return_value = account

    # scalars() calls in get_summary:
    # 1. get_account_in_workspace -> account_result
    # 2. current_rows -> [current_reach, current_views, current_interactions]
    # 3. prev_rows -> [prev_reach, prev_views, prev_interactions]
    # 4. latest_follower -> MagicMock(first=lambda: 1200)
    # 5. oldest_follower -> MagicMock(first=lambda: 1100)
    # 6. latest_fetched -> MagicMock(first=lambda: now)
    follower_mock = MagicMock()
    follower_mock.first.return_value = 1200
    old_follower_mock = MagicMock()
    old_follower_mock.first.return_value = 1100
    fetched_mock = MagicMock()
    fetched_mock.first.return_value = now

    session.scalars.side_effect = [
        account_result,
        [
            AccountInsightDaily(
                workspace_id=workspace_id,
                social_account_id=account_id,
                local_date=today - timedelta(days=i),
                metric=row.metric,
                value=row.value,
                fetched_at=now,
            )
            for i in range(7)
            for row in (current_reach, current_views, current_interactions)
        ],
        [
            AccountInsightDaily(
                workspace_id=workspace_id,
                social_account_id=account_id,
                local_date=today - timedelta(days=i + 7),
                metric=row.metric,
                value=row.value,
                fetched_at=now,
            )
            for i in range(7)
            for row in (prev_reach, prev_views, prev_interactions)
        ],
        follower_mock,
        old_follower_mock,
        fetched_mock,
    ]

    summary = service.get_summary(
        session, workspace_id, account_id, range_days=7, clock=FrozenClock(now)
    )
    assert summary.status == "ok"
    assert summary.reach == 3500
    assert summary.views == 5600
    assert summary.interactions == 350
    # reach delta: (500 - 400) / 400 = +25%
    assert summary.reach_delta_pct == 25
    # views delta: (800 - 400) / 400 = +100%
    assert summary.views_delta_pct == 100
    # interactions delta: (50 - 25) / 25 = +100%
    assert summary.interactions_delta_pct == 100
    assert summary.follower_count == 1200
    assert summary.follower_delta is None  # follower history is not complete
    assert len(summary.sparkline) == 7


def test_eligible_requires_enabled_provider(monkeypatch: object) -> None:
    from unittest.mock import patch

    from app.core.config import Settings
    from app.insights.jobs import _eligible

    mock_account = SocialAccount(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        provider_kind="mock",
        external_account_id="mock_1",
        username="demo",
        status="connected",
        granted_scopes=[],
    )
    meta_only = Settings(_env_file=None).model_copy(update={"instagram_enabled_providers": "meta"})
    with patch("app.insights.jobs.get_settings", return_value=meta_only):
        assert _eligible(mock_account) is False

    mock_enabled = Settings(_env_file=None).model_copy(
        update={"instagram_enabled_providers": "mock"}
    )
    with patch("app.insights.jobs.get_settings", return_value=mock_enabled):
        assert _eligible(mock_account) is True
