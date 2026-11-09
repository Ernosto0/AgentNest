import { useState, type PointerEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { AlertIcon, ChartIcon, InfoIcon, LinkIcon, SpinnerIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { FOCUS, InlineNotice, Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";
import { useInsightsSummary, type InsightsSummary } from "./hooks";

type Range = "7d" | "28d";
type Series = "reach" | "views";

const SERIES: { key: Series; swatch: string; dot: string; dashed: boolean }[] = [
  { key: "reach", swatch: "h-0.5 w-4 rounded-full bg-chart-1", dot: "bg-chart-1", dashed: false },
  { key: "views", swatch: "h-0 w-4 border-t-2 border-dashed border-chart-2", dot: "bg-chart-2", dashed: true },
];

/** The smallest 1/2/5 × 10ⁿ step at or above `value`, so axis labels are round numbers. */
function niceCeiling(value: number): number {
  if (value <= 1) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find((f) => f * magnitude >= value)!;
  return step * magnitude;
}

function DeltaPill({ delta, range }: { delta: number | null | undefined; range: Range }) {
  const { t } = useTranslation();
  if (delta === null || delta === undefined) return null;
  const tone = delta > 0 ? "bg-success-subtle text-success" : delta < 0 ? "bg-danger-subtle text-danger" : "bg-surface-subtle text-secondary";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-px text-[11px] font-semibold tabular-nums ${tone}`}
      title={t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
    >
      {delta !== 0 ? <span aria-hidden="true" className="text-[0.5625rem]">{delta > 0 ? "▲" : "▼"}</span> : null}
      <span>{delta > 0 ? `+${delta}%` : `${delta}%`}</span>
    </span>
  );
}

/**
 * Daily reach and views on one shared count axis (same unit). Hover or touch shows a crosshair
 * with both values; a visually hidden table carries the same numbers for assistive technology.
 * Series without any data are neither drawn nor listed in the legend.
 */
function TrendChart({ points }: { points: InsightsSummary["sparkline"] }) {
  const { t, i18n } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  if (points.length < 2) return null;

  const fmt = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const dateLabel = (date: string) =>
    new Date(`${date}T12:00:00Z`).toLocaleDateString(i18n.language, { day: "numeric", month: "short", timeZone: "UTC" });
  const series = SERIES.filter((s) => points.some((p) => p[s.key] !== null));
  const max = niceCeiling(Math.max(...points.map((p) => Math.max(p.reach ?? 0, p.views ?? 0))));
  const ticks = Number.isInteger(max / 2) ? [max, max / 2, 0] : [max, 0];
  const x = (i: number) => (i / (points.length - 1)) * 100;
  const y = (v: number) => 4 + (1 - v / max) * 92;
  const path = (key: Series) =>
    points
      .map((p, i) => {
        const value = p[key];
        if (value === null) return "";
        const prev = i > 0 ? points[i - 1]![key] : null;
        return `${prev !== null && i > 0 ? "L" : "M"} ${x(i).toFixed(2)},${y(value).toFixed(2)}`;
      })
      .join(" ");

  const onPointer = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    setActive(Math.round(ratio * (points.length - 1)));
  };
  const point = active === null ? null : points[active]!;
  // With few points, or a value whose neighbours are missing, a line alone hides the data: mark it.
  const markAll = points.length <= 10;
  const isolated = (key: Series, i: number) =>
    points[i]![key] !== null && (i === 0 || points[i - 1]![key] === null) && (i === points.length - 1 || points[i + 1]![key] === null);
  const flip = active !== null && active > (points.length - 1) / 2;

  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-secondary">
        <span className="font-semibold text-primary">{t("home.insights.trendTitle")}</span>
        <span className="flex items-center gap-3">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className={s.swatch} />
              {t(`home.insights.${s.key}`)}
            </span>
          ))}
        </span>
      </figcaption>
      <div aria-hidden="true" className="relative h-32">
        {ticks.map((tick) => (
          <div key={tick} className="absolute inset-x-0 flex items-center gap-2" style={{ top: `${y(tick)}%`, transform: "translateY(-50%)" }}>
            <span className="w-7 shrink-0 text-right text-[0.6875rem] text-secondary tabular-nums">{fmt.format(tick)}</span>
            <span className={`h-px flex-1 ${tick === 0 ? "bg-border" : "border-t border-dashed border-border"}`} />
          </div>
        ))}
        <div
          className="absolute inset-y-0 right-0 left-9 touch-pan-y"
          onPointerMove={onPointer}
          onPointerDown={onPointer}
          onPointerLeave={() => setActive(null)}
        >
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
            {series.map((s) => (
              <path
                key={s.key}
                d={path(s.key)}
                fill="none"
                stroke={s.key === "reach" ? "var(--an-chart-1)" : "var(--an-chart-2)"}
                strokeWidth="2"
                strokeDasharray={s.dashed ? "5 4" : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {active !== null ? (
              <line x1={x(active)} x2={x(active)} y1="0" y2="96" stroke="var(--an-text-secondary)" strokeOpacity="0.35" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ) : null}
          </svg>
          {series.flatMap((s) =>
            points.map((p, i) =>
              p[s.key] !== null && (markAll || isolated(s.key, i)) && i !== active ? (
                <span
                  key={`${s.key}-${p.date}`}
                  className={`pointer-events-none absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface ${s.dot}`}
                  style={{ left: `${x(i)}%`, top: `${y(p[s.key]!)}%` }}
                />
              ) : null,
            ),
          )}
          {point
            ? series.map((s) =>
                point[s.key] === null ? null : (
                  <span
                    key={s.key}
                    className={`pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface ${s.dot}`}
                    style={{ left: `${x(active!)}%`, top: `${y(point[s.key]!)}%` }}
                  />
                ),
              )
            : null}
          {point ? (
            <div
              className="pointer-events-none absolute top-1 z-10 min-w-32 rounded-lg bg-navigation px-3 py-2 text-xs text-navigation-text shadow-float"
              style={{ left: `${x(active!)}%`, transform: `translateX(${flip ? "calc(-100% - 0.5rem)" : "0.5rem"})` }}
            >
              <p className="mb-1 font-semibold text-white">{dateLabel(point.date)}</p>
              {SERIES.map((s) => (
                <p key={s.key} className="flex justify-between gap-4">
                  <span>{t(`home.insights.${s.key}`)}</span>
                  <span className="font-semibold text-white tabular-nums">{point[s.key] === null ? "—" : fmt.format(point[s.key]!)}</span>
                </p>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <div aria-hidden="true" className="flex justify-between pl-9 text-[0.6875rem] text-secondary">
        <span>{dateLabel(points[0]!.date)}</span>
        <span>{dateLabel(points[points.length - 1]!.date)}</span>
      </div>
      <table className="sr-only">
        <caption>{t("home.insights.trendTitle")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("home.insights.date")}</th>
            <th scope="col">{t("home.insights.reach")}</th>
            <th scope="col">{t("home.insights.views")}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <th scope="row">{dateLabel(p.date)}</th>
              <td>{p.reach === null ? t("core.unavailable") : fmt.format(p.reach)}</td>
              <td>{p.views === null ? t("core.unavailable") : fmt.format(p.views)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function Kpi({ label, value, missing, delta }: { label: string; value: ReactNode; missing: boolean; delta?: ReactNode }) {
  return (
    <div className="min-w-0 @2xl:flex @2xl:items-end @2xl:justify-between @2xl:gap-3 @2xl:py-3 @2xl:first:pt-0 @2xl:last:pb-0">
      <div className="min-w-0">
        <p className="truncate text-xs text-secondary">{label}</p>
        <p
          className={`font-heading leading-8 font-bold tracking-tight tabular-nums ${
            missing ? "text-xl text-secondary/60" : "text-2xl text-primary"
          }`}
        >
          {value}
        </p>
      </div>
      {delta ? <div className="mt-0.5 @2xl:mt-0 @2xl:mb-1">{delta}</div> : null}
    </div>
  );
}

/**
 * Instagram performance for one account: reach, views and interactions against the previous
 * period. It sits in the side column or in a full-width band, so its layout follows its own
 * width (container queries) rather than the viewport.
 */
export function InsightsPerformanceCard({
  workspaceId,
  accounts,
  isOwner,
}: {
  workspaceId: string;
  accounts: SocialAccount[];
  isOwner: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [range, setRange] = useState<Range>("7d");
  const activeAccounts = accounts.filter((a) => a.status !== "disconnected");
  const [selectedId, setSelectedId] = useState<string | undefined>(activeAccounts[0]?.id);
  const activeAccount = activeAccounts.find((a) => a.id === selectedId) ?? activeAccounts[0];
  const summaryQuery = useInsightsSummary(workspaceId, activeAccount?.id, range);
  const summary = summaryQuery.data;

  if (activeAccounts.length === 0) return null;

  const days = range === "7d" ? 7 : 28;
  const formatNumber = (num: number | null | undefined) =>
    num == null ? (
      <>
        <span aria-hidden="true">—</span>
        <span className="sr-only">{t("core.unavailable")}</span>
      </>
    ) : (
      new Intl.NumberFormat(i18n.language).format(num)
    );
  const segment = (value: Range, label: string) => (
    <button
      type="button"
      onClick={() => setRange(value)}
      aria-pressed={range === value}
      className={`min-h-8 rounded-md px-2.5 text-xs font-semibold transition-colors ${FOCUS} ${
        range === value ? "bg-surface text-primary ring-1 ring-border" : "text-secondary hover:text-primary"
      }`}
    >
      {label}
    </button>
  );

  let body: ReactNode;
  if (summaryQuery.isPending) {
    body = <SkeletonRows label={t("home.insights.loading")} rows={3} />;
  } else if (summaryQuery.isError) {
    body = (
      <InlineNotice
        tone="attention"
        icon={<AlertIcon />}
        title={t("home.insights.errorLoading")}
        action={
          <button
            type="button"
            onClick={() => void summaryQuery.refetch()}
            disabled={summaryQuery.isFetching}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-surface px-3 text-xs font-semibold text-primary ring-1 ring-border transition-colors ring-inset hover:bg-surface-subtle disabled:opacity-60 ${FOCUS}`}
          >
            {summaryQuery.isFetching ? <SpinnerIcon aria-hidden="true" className="motion-safe:animate-spin" /> : null}
            {t("common.retry")}
          </button>
        }
      />
    );
  } else if (summary?.status === "not_granted") {
    body = (
      <InlineNotice
        tone="attention"
        icon={<AlertIcon />}
        title={t("home.insights.scopeNotGrantedTitle")}
        action={
          isOwner ? (
            <Link
              to={`/w/${workspaceId}/more/settings/connections`}
              className={`inline-flex min-h-10 items-center gap-2 rounded-control bg-action px-4 text-metadata font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
            >
              <LinkIcon aria-hidden="true" />
              {t("home.insights.reconnectCta")}
            </Link>
          ) : undefined
        }
      >
        {t("home.insights.scopeNotGrantedDesc")}
      </InlineNotice>
    );
  } else if (summary?.status === "below_threshold") {
    body = <InlineNotice tone="neutral" icon={<InfoIcon />} title={t("home.insights.belowThresholdDesc")} />;
  } else if (summary?.status === "syncing") {
    body = (
      <InlineNotice tone="info" icon={<SpinnerIcon className="motion-safe:animate-spin" />} title={t("home.insights.syncingTitle")}>
        {t("home.insights.syncingDesc")}
      </InlineNotice>
    );
  } else {
    const kpis = [
      { key: "reach", label: t("home.insights.reach"), value: summary?.reach, delta: summary?.reach_delta_pct },
      { key: "views", label: t("home.insights.views"), value: summary?.views, delta: summary?.views_delta_pct },
      { key: "interactions", label: t("home.insights.interactions"), value: summary?.interactions, delta: summary?.interactions_delta_pct },
    ];
    body = (
      <div className="flex flex-col gap-4">
        {summary?.status === "partial" ? (
          <p role="status" data-testid="insights-partial" className="flex items-start gap-2 text-xs leading-5 text-secondary">
            <InfoIcon aria-hidden="true" className="mt-0.5 shrink-0 text-sm text-info" />
            <span>{t("home.insights.partial", { current: summary.current_days_covered, previous: summary.previous_days_covered, days })}</span>
          </p>
        ) : null}
        <div className="grid gap-5 @2xl:grid-cols-[minmax(0,5fr)_minmax(0,8fr)] @2xl:gap-10">
          <div className="flex flex-col gap-3">
            <div data-testid="insights-kpis" className="grid grid-cols-3 gap-3 @2xl:flex @2xl:flex-col @2xl:gap-0 @2xl:divide-y @2xl:divide-border">
              {kpis.map((kpi) => (
                <Kpi
                  key={kpi.key}
                  label={kpi.label}
                  value={formatNumber(kpi.value)}
                  missing={kpi.value == null}
                  delta={<DeltaPill delta={kpi.delta} range={range} />}
                />
              ))}
            </div>
            {summary?.follower_count !== null && summary?.follower_count !== undefined ? (
              <p className="text-xs text-secondary">
                <span className="font-semibold text-primary tabular-nums">{formatNumber(summary.follower_count)}</span>{" "}
                {t("home.insights.followersTotal")}
                {summary.follower_delta !== null && summary.follower_delta !== undefined ? (
                  <span className={`ml-1 font-medium ${summary.follower_delta >= 0 ? "text-success" : "text-danger"}`}>
                    ({summary.follower_delta >= 0 ? `+${summary.follower_delta}` : summary.follower_delta})
                  </span>
                ) : null}
              </p>
            ) : null}
            {kpis.some((kpi) => kpi.delta !== null && kpi.delta !== undefined) ? (
              <p className="text-[0.6875rem] text-secondary">{t("home.insights.vsPrevPeriod", { days })}</p>
            ) : null}
          </div>
          {summary?.sparkline && summary.sparkline.length > 1 ? <TrendChart points={summary.sparkline} /> : null}
        </div>
      </div>
    );
  }

  return (
    <Panel aria-labelledby="home-insights-title" data-testid="insights-performance-card" className="@container gap-4">
      <PanelHeading
        id="home-insights-title"
        icon={<ChartIcon />}
        title={t("home.insights.title")}
        wrap
        meta={activeAccount?.is_simulated ? <SimulatedBadge compact /> : undefined}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {activeAccounts.length > 1 ? (
              <select
                aria-label={t("home.insights.account")}
                value={activeAccount?.id}
                onChange={(e) => setSelectedId(e.target.value)}
                className={`min-h-8 max-w-44 truncate rounded-lg border border-border bg-surface px-2 text-xs! font-medium text-primary ${FOCUS}`}
              >
                {activeAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    @{a.username ?? "instagram"}
                  </option>
                ))}
              </select>
            ) : null}
            <div className="inline-flex rounded-lg bg-surface-subtle p-0.5">
              {segment("7d", t("home.insights.range7d"))}
              {segment("28d", t("home.insights.range28d"))}
            </div>
            <PanelLink to={`/w/${workspaceId}/more/reports`}>{t("home.insights.fullReportsLink")}</PanelLink>
          </div>
        }
      />
      {body}
    </Panel>
  );
}
