"""Instagram Insights service: ingestion, snapshots, aggregations and queries."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.insights.models import AccountInsightDaily, AudienceSnapshot, MediaInsightSnapshot
from app.insights.schemas import (
    AudienceOut,
    InsightsContentItemOut,
    InsightsContentListOut,
    InsightsSummaryOut,
    SparklinePoint,
)
from app.integrations.instagram import queries
from app.integrations.instagram.errors import ProviderPermissionError
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import account_ref, get_provider

INSIGHT_METRICS = [
    "reach",
    "views",
    "total_interactions",
    "accounts_engaged",
    "follower_count",
    "profile_links_taps",
]


def sync_account_daily(
    db: Session,
    clock: Clock,
    settings: Settings,
    account: SocialAccount,
    *,
    days: list[date] | None = None,
    heartbeat: Callable[[], None] | None = None,
) -> None:
    """Collect exact daily windows before writing; the caller owns the transaction.

    One-day requests also keep provider ``total_value`` responses from being stored
    as though an entire multi-day aggregate belonged to a single day.
    """
    if not settings.insights_enabled or account.provider_kind not in settings.instagram_providers:
        return

    # Check permission scope
    if account.provider_kind == "meta" and "instagram_business_manage_insights" not in (
        account.granted_scopes or []
    ):
        return

    provider = get_provider(
        account.provider_kind,
        settings=settings,
        session_factory=lambda: db,
        clock=clock,
    )
    ref = account_ref(account, settings)

    now = clock.now()
    days = days if days is not None else [now.date() - timedelta(days=1), now.date()]
    metrics = []
    for day in days:
        since = datetime.combine(day, time.min, UTC)
        until = min(since + timedelta(days=1) - timedelta(seconds=1), now)
        try:
            metrics.extend(
                provider.get_account_insights(
                    ref,
                    INSIGHT_METRICS,
                    since=since,
                    until=until,
                )
            )
        except ProviderPermissionError:
            return
        if heartbeat:
            heartbeat()

    for item in metrics:
        item_date = date.fromisoformat(item.date)
        stmt = (
            insert(AccountInsightDaily)
            .values(
                id=uuid.uuid4(),
                workspace_id=account.workspace_id,
                social_account_id=account.id,
                local_date=item_date,
                metric=item.metric,
                value=item.value,
                fetched_at=now,
                is_simulated=account.is_simulated,
            )
            .on_conflict_do_update(
                constraint="uq_account_insight_daily_metric",
                set_={
                    "value": item.value,
                    "fetched_at": now,
                    "updated_at": func.now(),
                },
            )
        )
        db.execute(stmt)
    db.flush()


def capture_media_snapshot(
    db: Session,
    clock: Clock,
    settings: Settings,
    account: SocialAccount,
    ig_media_id: str,
    media_kind: str,
    content_item_id: uuid.UUID | None = None,
    is_final: bool = False,
) -> None:
    """Snapshot media performance for a post or story."""
    if not settings.insights_enabled or account.provider_kind not in settings.instagram_providers:
        return

    provider = get_provider(
        account.provider_kind,
        settings=settings,
        session_factory=lambda: db,
        clock=clock,
    )
    ref = account_ref(account, settings)
    now = clock.now()

    try:
        data = provider.get_media_insights(ref, ig_media_id, media_kind)
    except ProviderPermissionError:
        return

    for metric_name, val in data.metrics.items():
        snapshot = MediaInsightSnapshot(
            id=uuid.uuid4(),
            workspace_id=account.workspace_id,
            social_account_id=account.id,
            content_item_id=content_item_id,
            ig_media_id=ig_media_id,
            media_kind=media_kind,
            metric=metric_name,
            value=val,
            captured_at=now,
            is_final=is_final,
            is_simulated=account.is_simulated,
        )
        db.add(snapshot)
    db.flush()


def sync_account_audience(
    db: Session,
    clock: Clock,
    settings: Settings,
    account: SocialAccount,
) -> None:
    """Fetch audience demographics and active hours, saving weekly snapshots."""
    if not settings.insights_enabled or account.provider_kind not in settings.instagram_providers:
        return

    provider = get_provider(
        account.provider_kind,
        settings=settings,
        session_factory=lambda: db,
        clock=clock,
    )
    ref = account_ref(account, settings)
    now = clock.now()
    today = now.date()

    try:
        data = provider.get_audience(ref)
    except ProviderPermissionError:
        return

    if data.online_followers:
        stmt = (
            insert(AudienceSnapshot)
            .values(
                id=uuid.uuid4(),
                workspace_id=account.workspace_id,
                social_account_id=account.id,
                captured_on=today,
                kind="online_followers",
                payload_json=data.online_followers,
                is_simulated=account.is_simulated,
            )
            .on_conflict_do_update(
                constraint="uq_audience_snapshots_account_day_kind",
                set_={"payload_json": data.online_followers, "updated_at": func.now()},
            )
        )
        db.execute(stmt)

    if data.demographics:
        stmt = (
            insert(AudienceSnapshot)
            .values(
                id=uuid.uuid4(),
                workspace_id=account.workspace_id,
                social_account_id=account.id,
                captured_on=today,
                kind="demographics",
                payload_json=data.demographics,
                is_simulated=account.is_simulated,
            )
            .on_conflict_do_update(
                constraint="uq_audience_snapshots_account_day_kind",
                set_={"payload_json": data.demographics, "updated_at": func.now()},
            )
        )
        db.execute(stmt)
    db.flush()


def get_summary(
    db: Session,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    range_days: int = 7,
    clock: Clock | None = None,
) -> InsightsSummaryOut:
    """Aggregate covered daily windows; unknown history stays unavailable."""
    account = queries.get_account_in_workspace(db, workspace_id, account_id)
    if account is None:
        raise AppError("NOT_FOUND")

    # Scope check
    has_scope = account.provider_kind == "mock" or "instagram_business_manage_insights" in (
        account.granted_scopes or []
    )
    if not has_scope:
        return InsightsSummaryOut(
            account_id=account_id,
            range="7d" if range_days == 7 else "28d",
            status="not_granted",
            updated_at=None,
            reach=0,
            reach_delta_pct=None,
            views=0,
            views_delta_pct=None,
            interactions=0,
            interactions_delta_pct=None,
            follower_count=None,
            follower_delta=None,
            sparkline=[],
            is_simulated=account.is_simulated,
        )

    now_date = clock.now().date() if clock else date.today()
    current_start = now_date - timedelta(days=range_days)
    previous_start = current_start - timedelta(days=range_days)

    # Query daily metrics in current period
    current_stmt = select(AccountInsightDaily).where(
        AccountInsightDaily.workspace_id == workspace_id,
        AccountInsightDaily.social_account_id == account_id,
        AccountInsightDaily.local_date > current_start,
        AccountInsightDaily.local_date <= now_date,
    )
    current_rows = list(db.scalars(current_stmt))

    # Query daily metrics in previous period (for delta)
    prev_stmt = select(AccountInsightDaily).where(
        AccountInsightDaily.workspace_id == workspace_id,
        AccountInsightDaily.social_account_id == account_id,
        AccountInsightDaily.local_date > previous_start,
        AccountInsightDaily.local_date <= current_start,
    )
    prev_rows = list(db.scalars(prev_stmt))

    if not current_rows and not prev_rows:
        return InsightsSummaryOut(
            account_id=account_id,
            range="7d" if range_days == 7 else "28d",
            status="syncing",
            updated_at=None,
            reach=0,
            reach_delta_pct=None,
            views=0,
            views_delta_pct=None,
            interactions=0,
            interactions_delta_pct=None,
            follower_count=None,
            follower_delta=None,
            sparkline=[],
            is_simulated=account.is_simulated,
        )

    # Sum metrics
    cur_reach = sum(r.value for r in current_rows if r.metric == "reach")
    prev_reach = sum(r.value for r in prev_rows if r.metric == "reach")

    cur_views = sum(r.value for r in current_rows if r.metric == "views")
    prev_views = sum(r.value for r in prev_rows if r.metric == "views")

    cur_interactions = sum(r.value for r in current_rows if r.metric == "total_interactions")
    prev_interactions = sum(r.value for r in prev_rows if r.metric == "total_interactions")

    def covered(rows: list[AccountInsightDaily], metric: str) -> bool:
        return len({r.local_date for r in rows if r.metric == metric}) == range_days

    required = {"reach", "views", "total_interactions"}

    def days_covered(rows: list[AccountInsightDaily]) -> int:
        per_day: dict[date, set[str]] = {}
        for row in rows:
            per_day.setdefault(row.local_date, set()).add(row.metric)
        return sum(required <= metrics for metrics in per_day.values())

    current_coverage = days_covered(current_rows)
    previous_coverage = days_covered(prev_rows)

    def _delta(cur: int, prev: int, metric: str) -> int | None:
        if not covered(current_rows, metric) or not covered(prev_rows, metric):
            return None
        if prev == 0:
            return 0 if cur == 0 else None
        return round(((cur - prev) / prev) * 100)

    # Follower count from latest snapshot
    latest_follower = db.scalars(
        select(AccountInsightDaily.value)
        .where(
            AccountInsightDaily.workspace_id == workspace_id,
            AccountInsightDaily.social_account_id == account_id,
            AccountInsightDaily.metric == "follower_count",
        )
        .order_by(desc(AccountInsightDaily.local_date))
        .limit(1)
    ).first()

    oldest_follower = db.scalars(
        select(AccountInsightDaily.value)
        .where(
            AccountInsightDaily.workspace_id == workspace_id,
            AccountInsightDaily.social_account_id == account_id,
            AccountInsightDaily.metric == "follower_count",
            AccountInsightDaily.local_date > current_start,
        )
        .order_by(AccountInsightDaily.local_date.asc())
        .limit(1)
    ).first()

    follower_delta = (
        (latest_follower - oldest_follower)
        if latest_follower is not None
        and oldest_follower is not None
        and covered(current_rows, "follower_count")
        else None
    )

    # Sparkline: group by date
    days_map: dict[str, dict[str, int | None]] = {}
    for i in range(range_days):
        d_str = (current_start + timedelta(days=i + 1)).isoformat()
        days_map[d_str] = {"reach": None, "views": None}

    for r in current_rows:
        d_str = r.local_date.isoformat()
        if d_str in days_map and r.metric in ("reach", "views"):
            days_map[d_str][r.metric] = r.value

    sparkline = [
        SparklinePoint(date=d, reach=vals["reach"], views=vals["views"])
        for d, vals in sorted(days_map.items())
    ]

    latest_fetched = db.scalars(
        select(AccountInsightDaily.fetched_at)
        .where(
            AccountInsightDaily.workspace_id == workspace_id,
            AccountInsightDaily.social_account_id == account_id,
        )
        .order_by(desc(AccountInsightDaily.fetched_at))
        .limit(1)
    ).first()

    return InsightsSummaryOut(
        account_id=account_id,
        range="7d" if range_days == 7 else "28d",
        status="ok"
        if current_coverage == range_days and previous_coverage == range_days
        else "partial",
        current_days_covered=current_coverage,
        previous_days_covered=previous_coverage,
        updated_at=latest_fetched,
        reach=cur_reach if covered(current_rows, "reach") else None,
        reach_delta_pct=_delta(cur_reach, prev_reach, "reach"),
        views=cur_views if covered(current_rows, "views") else None,
        views_delta_pct=_delta(cur_views, prev_views, "views"),
        interactions=cur_interactions if covered(current_rows, "total_interactions") else None,
        interactions_delta_pct=_delta(cur_interactions, prev_interactions, "total_interactions"),
        follower_count=latest_follower,
        follower_delta=follower_delta,
        sparkline=sparkline,
        is_simulated=account.is_simulated,
    )


def get_content_insights(
    db: Session,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    kind: str | None = None,
    limit: int = 10,
) -> InsightsContentListOut:
    """Return top/recent media performance items joined with content items."""
    account = queries.get_account_in_workspace(db, workspace_id, account_id)
    if account is None:
        raise AppError("NOT_FOUND")

    from app.content.models import ContentItem

    # Query distinct ig_media_ids
    stmt = select(
        MediaInsightSnapshot.ig_media_id,
        MediaInsightSnapshot.media_kind,
        MediaInsightSnapshot.content_item_id,
    ).where(
        MediaInsightSnapshot.workspace_id == workspace_id,
        MediaInsightSnapshot.social_account_id == account_id,
    )
    if kind:
        stmt = stmt.where(
            MediaInsightSnapshot.media_kind
            == (f"{kind}_image" if not kind.endswith("_image") else kind)
        )

    stmt = stmt.group_by(
        MediaInsightSnapshot.ig_media_id,
        MediaInsightSnapshot.media_kind,
        MediaInsightSnapshot.content_item_id,
    ).limit(limit)

    distinct_media = db.execute(stmt).all()

    items: list[InsightsContentItemOut] = []
    for ig_id, media_kind, item_id in distinct_media:
        # Fetch metrics for this media id (latest values)
        snapshots = list(
            db.scalars(
                select(MediaInsightSnapshot)
                .where(
                    MediaInsightSnapshot.workspace_id == workspace_id,
                    MediaInsightSnapshot.ig_media_id == ig_id,
                )
                .order_by(desc(MediaInsightSnapshot.captured_at))
            )
        )
        metrics: dict[str, int] = {}
        for s in snapshots:
            if s.metric not in metrics:
                metrics[s.metric] = s.value

        content_title: str | None = None
        published_at: datetime | None = None
        if item_id:
            ci = db.get(ContentItem, item_id)
            if ci:
                content_title = ci.title
                published_at = ci.published_at

        items.append(
            InsightsContentItemOut(
                content_item_id=item_id,
                ig_media_id=ig_id,
                media_kind=media_kind,
                title=content_title or f"Media {ig_id[:8]}",
                published_at=published_at,
                reach=metrics.get("reach", 0),
                views=metrics.get("views", 0),
                total_interactions=metrics.get("total_interactions", 0),
                metrics=metrics,
                is_simulated=account.is_simulated,
            )
        )

    # Sort by reach desc
    items.sort(key=lambda x: x.reach, reverse=True)
    return InsightsContentListOut(items=items)


def get_audience_data(
    db: Session,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
) -> AudienceOut:
    """Return audience demographics and online follower distribution."""
    account = queries.get_account_in_workspace(db, workspace_id, account_id)
    if account is None:
        raise AppError("NOT_FOUND")

    latest_follower = db.scalars(
        select(AccountInsightDaily.value)
        .where(
            AccountInsightDaily.workspace_id == workspace_id,
            AccountInsightDaily.social_account_id == account_id,
            AccountInsightDaily.metric == "follower_count",
        )
        .order_by(desc(AccountInsightDaily.local_date))
        .limit(1)
    ).first()

    if latest_follower is not None and latest_follower < 100:
        return AudienceOut(
            status="below_threshold",
            follower_count=latest_follower,
            online_hours=None,
            best_posting_window=None,
            demographics=None,
        )

    online_snap = db.scalars(
        select(AudienceSnapshot)
        .where(
            AudienceSnapshot.workspace_id == workspace_id,
            AudienceSnapshot.social_account_id == account_id,
            AudienceSnapshot.kind == "online_followers",
        )
        .order_by(desc(AudienceSnapshot.captured_on))
        .limit(1)
    ).first()

    demo_snap = db.scalars(
        select(AudienceSnapshot)
        .where(
            AudienceSnapshot.workspace_id == workspace_id,
            AudienceSnapshot.social_account_id == account_id,
            AudienceSnapshot.kind == "demographics",
        )
        .order_by(desc(AudienceSnapshot.captured_on))
        .limit(1)
    ).first()

    online_hours = online_snap.payload_json if online_snap else None
    best_window = "19:00 - 21:00" if online_hours else None

    return AudienceOut(
        status="ok",
        follower_count=latest_follower or (1420 if account.is_simulated else None),
        online_hours=online_hours,
        best_posting_window=best_window,
        demographics=demo_snap.payload_json if demo_snap else None,
    )
