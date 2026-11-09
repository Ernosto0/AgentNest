import { useState, type PointerEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { AlertIcon, ChartIcon, InfoIcon, LinkIcon, SpinnerIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { FOCUS, InlineNotice, Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";
import { useInsightsSummary, type InsightsSummary } from "./hooks";

type Range = "7d" | "28d";

function DeltaPill({ delta, range }: { delta: number | null | undefined; range: Range }) {
  const { t } = useTranslation();
  if (delta === null || delta === undefined) return null;
  const tone = delta > 0 ? "bg-success-subtle text-success" : delta < 0 ? "bg-danger-subtle text-danger" : "bg-surface-subtle text-secondary";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${tone}`}
      title={t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
    >
      {delta !== 0 ? <span aria-hidden="true" className="text-[0.625rem]">{delta > 0 ? "▲" : "▼"}</span> : null}
      <span>{delta > 0 ? `+${delta}%` : `${delta}%`}</span>
    </span>
  );
}

/**
 * Daily reach and views on one shared count axis (same unit). Hover or touch shows a crosshair
 * with both values; a visually hidden table carries the same numbers for assistive technology.
 */
function TrendChart({ points }: { points: InsightsSummary["sparkline"] }) {
  const { t, i18n } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  if (points.length < 2) return null;

  const fmt = new Intl.NumberFormat(i18n.language);
  const dateLabel = (date: string) =>
    new Date(`${date}T12:00:00Z`).toLocaleDateString(i18n.language, { day: "numeric", month: "short", timeZone: "UTC" });
  const max = Math.max(...points.map((p) => Math.max(p.reach ?? 0, p.views ?? 0)), 1);
  const x = (i: number) => (i / (points.length - 1)) * 100;
  const y = (v: number) => 6 + (1 - v / max) * 88;
  const path = (key: "reach" | "views") =>
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

  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-secondary">
        <span className="font-semibold">{t("home.insights.trendTitle")}</span>
        <span className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0.5 w-4 rounded-full bg-chart-1" />
            {t("home.insights.reach")}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0 w-4 border-t-2 border-dashed border-chart-2" />
            {t("home.insights.views")}
          </span>
        </span>
      </figcaption>
      <div
        className="relative h-36 touch-pan-y"
        onPointerMove={onPointer}
        onPointerDown={onPointer}
        onPointerLeave={() => setActive(null)}
        aria-hidden="true"
      >
        <span className="absolute top-0 left-0 text-[0.6875rem] text-secondary tabular-nums">{fmt.format(max)}</span>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
          <line x1="0" x2="100" y1="94" y2="94" stroke="var(--an-border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          <line x1="0" x2="100" y1="50" y2="50" stroke="var(--an-border)" strokeWidth="1" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
          <path d={path("views")} fill="none" stroke="var(--an-chart-2)" strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          <path d={path("reach")} fill="none" stroke="var(--an-chart-1)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          {active !== null ? (
            <line x1={x(active)} x2={x(active)} y1="0" y2="94" stroke="var(--an-text-secondary)" strokeOpacity="0.4" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ) : null}
        </svg>
        {point
          ? (["reach", "views"] as const).map((key) =>
              point[key] === null ? null : (
                <span
                  key={key}
                  className={`pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface ${key === "reach" ? "bg-chart-1" : "bg-chart-2"}`}
                  style={{ left: `${x(active!)}%`, top: `${y(point[key]!)}%` }}
                />
              ),
            )
          : null}
        {point ? (
          <div
            className="pointer-events-none absolute top-5 z-10 min-w-32 rounded-lg bg-navigation px-3 py-2 text-xs text-navigation-text shadow-float"
            style={{ left: `${x(active!)}%`, transform: `translateX(${active! > (points.length - 1) / 2 ? "calc(-100% - 0.5rem)" : "0.5rem"})` }}
          >
            <p className="mb-1 font-semibold text-white">{dateLabel(point.date)}</p>
            <p className="flex justify-between gap-4">
              <span>{t("home.insights.reach")}</span>
              <span className="font-semibold text-white tabular-nums">{point.reach === null ? "—" : fmt.format(point.reach)}</span>
            </p>
            <p className="flex justify-between gap-4">
              <span>{t("home.insights.views")}</span>
              <span className="font-semibold text-white tabular-nums">{point.views === null ? "—" : fmt.format(point.views)}</span>
            </p>
          </div>
        ) : null}
      </div>
      <div aria-hidden="true" className="flex justify-between text-[0.6875rem] text-secondary">
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

function Kpi({ label, value, extra }: { label: string; value: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex min-w-0 items-end justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-metadata text-secondary">{label}</p>
        <p className="font-heading text-2xl leading-8 font-bold tracking-tight text-primary tabular-nums">{value}</p>
      </div>
      {extra}
    </div>
  );
}

/** Instagram performance for one account: reach, views and interactions against the previous period. */
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
      className={`min-h-9 rounded-md px-3 text-xs font-semibold transition-colors ${FOCUS} ${
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
    body = <InlineNotice tone="attention" icon={<AlertIcon />} title={t("home.insights.errorLoading")} />;
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
              className={`inline-flex min-h-11 items-center gap-2 rounded-control bg-action px-4 text-metadata font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
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
    body = (
      <div className="flex flex-col gap-4">
        {summary?.status === "partial" ? (
          <p role="status" className="rounded-xl bg-surface-subtle px-4 py-2.5 text-metadata text-secondary" data-testid="insights-partial">
            {t("home.insights.partial", { current: summary.current_days_covered, previous: summary.previous_days_covered, days })}
          </p>
        ) : null}
        <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,8fr)] lg:gap-10">
          <div data-testid="insights-kpis" className="flex flex-col divide-y divide-border">
            <Kpi label={t("home.insights.reach")} value={formatNumber(summary?.reach)} extra={<DeltaPill delta={summary?.reach_delta_pct} range={range} />} />
            <Kpi label={t("home.insights.views")} value={formatNumber(summary?.views)} extra={<DeltaPill delta={summary?.views_delta_pct} range={range} />} />
            <Kpi
              label={t("home.insights.interactions")}
              value={formatNumber(summary?.interactions)}
              extra={<DeltaPill delta={summary?.interactions_delta_pct} range={range} />}
            />
            {summary?.follower_count !== null && summary?.follower_count !== undefined ? (
              <p className="pt-3 text-metadata text-secondary">
                <span className="font-semibold text-primary tabular-nums">{formatNumber(summary.follower_count)}</span>{" "}
                {t("home.insights.followersTotal")}
                {summary.follower_delta !== null && summary.follower_delta !== undefined ? (
                  <span className={`ml-1 font-medium ${summary.follower_delta >= 0 ? "text-success" : "text-danger"}`}>
                    ({summary.follower_delta >= 0 ? `+${summary.follower_delta}` : summary.follower_delta})
                  </span>
                ) : null}
              </p>
            ) : null}
          </div>
          {summary?.sparkline && summary.sparkline.length > 1 ? <TrendChart points={summary.sparkline} /> : null}
        </div>
        <p className="text-xs text-secondary">{t("home.insights.vsPrevPeriod", { days })}</p>
      </div>
    );
  }

  return (
    <Panel aria-labelledby="home-insights-title" data-testid="insights-performance-card" className="gap-5">
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
                className={`min-h-9 rounded-lg border border-border bg-surface px-2 text-xs! font-medium text-primary ${FOCUS}`}
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
