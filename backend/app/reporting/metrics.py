"""``compute_metrics``: the numbers of a report, as SQL aggregations over persisted records.

INV-08: nothing here is estimated or model-generated. INV-01: every row set filters by
``workspace_id``. INV-19: the caller passes the period as UTC instants computed in the workspace
timezone (``app.reporting.periods``).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Numeric, cast, func, select, text
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.reporting.definitions import DEFINITIONS, DEFINITIONS_VERSION, Definition

MEDIAN_DECIMALS = 1


@dataclass(frozen=True)
class Metric:
    key: str
    # An integer count; for the median metric minutes (one decimal), or None without data.
    value: int | float | None
    # ``pending_approvals_now`` only: the count per approval action.
    breakdown: dict[str, int] | None = None
    has_simulated_data: bool = False

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"key": self.key, "value": self.value}
        if self.breakdown is not None:
            data["breakdown"] = self.breakdown
        return data


@dataclass(frozen=True)
class Metrics:
    metrics: tuple[Metric, ...]
    definitions_version: str = DEFINITIONS_VERSION
    by_key: dict[str, Metric] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_key", {m.key: m for m in self.metrics})

    @property
    def has_simulated_data(self) -> bool:
        """True when any record that contributes to a metric is simulated (INV-09)."""
        return any(m.has_simulated_data for m in self.metrics)

    def value(self, key: str) -> int | float | None:
        return self.by_key[key].value

    def as_list(self) -> list[dict[str, Any]]:
        return [m.as_dict() for m in self.metrics]


def _compute_one(
    session: Session,
    ctx: WorkspaceContext,
    definition: Definition,
    start: datetime,
    end: datetime,
    now: datetime,
) -> Metric:
    rows = definition.rows(session, ctx, start, end, now).subquery("rows")
    if definition.value == "median":
        stmt = select(
            func.count(),
            func.bool_or(rows.c.is_simulated),
            cast(func.percentile_cont(0.5).within_group(rows.c.measure), Numeric),
        )
        count, simulated, median = session.execute(stmt).one()
        value: int | float | None = (
            None if not count or median is None else round(float(median), MEDIAN_DECIMALS)
        )
        return Metric(definition.key, value, None, bool(simulated))
    count, simulated = session.execute(
        select(func.count(), func.bool_or(rows.c.is_simulated))
    ).one()
    breakdown = None
    if definition.grouped:
        grouped = session.execute(
            select(rows.c.group_key, func.count()).group_by(rows.c.group_key)
        ).all()
        breakdown = {str(key): int(n) for key, n in sorted(grouped)}
    return Metric(definition.key, int(count), breakdown, bool(simulated))


def compute_metrics(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Metrics:
    """All metrics for ``[start, end)``; snapshot metrics are as of ``now``.

    Runs in a read-only savepoint: the database refuses any write inside it, and the savepoint is
    rolled back so the caller's transaction is left exactly as it was (it commits nothing).
    """
    session.flush()
    savepoint = session.begin_nested()
    try:
        session.execute(text("SET LOCAL transaction_read_only = on"))
        computed = tuple(_compute_one(session, ctx, d, start, end, now) for d in DEFINITIONS)
    finally:
        savepoint.rollback()
    return Metrics(computed)
