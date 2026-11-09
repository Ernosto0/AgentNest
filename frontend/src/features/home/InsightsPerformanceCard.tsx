import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Card } from "@/components/Card";
import { ChartIcon, LinkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useInsightsSummary, type InsightsSummary } from "./hooks";

interface InsightsPerformanceCardProps {
  workspaceId: string;
  accounts: SocialAccount[];
  isOwner: boolean;
}

function DeltaPill({ delta, range }: { delta: number | null | undefined; range: "7d" | "28d" }) {
  const { t } = useTranslation();
  if (delta === null || delta === undefined) {
    return <span className="text-xs text-secondary">—</span>;
  }
  const isPositive = delta > 0;
  const isZero = delta === 0;
  const colorClass = isZero
    ? "text-stone-500 bg-stone-100 dark:bg-stone-800"
    : isPositive
    ? "text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40"
    : "text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40";

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium ${colorClass}`}
      title={t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
    >
      <span>{isPositive ? "▲" : isZero ? "" : "▼"}</span>
      <span>{isPositive ? `+${delta}%` : `${delta}%`}</span>
    </span>
  );
}

function Sparkline({
  points,
}: {
  points: InsightsSummary["sparkline"];
}) {
  const { t } = useTranslation();
  if (points.length < 2) return null;

  const width = 360;
  const height = 70;
  const padX = 12;
  const padY = 8;
  const maxVal = Math.max(...points.map((p) => Math.max(p.reach ?? 0, p.views ?? 0)), 1);

  const coords = points.map((p, i) => {
    const x = padX + (i / (points.length - 1)) * (width - 2 * padX);
    const yReach = p.reach === null ? null : height - padY - (p.reach / maxVal) * (height - 2 * padY);
    const yViews = p.views === null ? null : height - padY - (p.views / maxVal) * (height - 2 * padY);
    return { x, yReach, yViews, ...p };
  });

  const path = (key: "yReach" | "yViews") => coords.map((c, index) =>
    c[key] === null ? "" : `${index > 0 && coords[index - 1]![key] !== null ? "L" : "M"} ${c.x.toFixed(1)},${c[key].toFixed(1)}`,
  ).join(" ");
  const reachD = path("yReach");
  const viewsD = path("yViews");

  return (
    <div className="mt-4 border-t border-stone-200/80 pt-3 dark:border-stone-800">
      <div className="mb-1 flex items-center justify-between text-xs text-stone-500 dark:text-stone-400">
        <span className="font-medium">{t("home.insights.trendTitle")}</span>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-sky-500" />
            {t("home.insights.reach")}
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-violet-500" />
            {t("home.insights.views")}
          </span>
        </div>
      </div>
      <div className="w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-16 w-full overflow-visible"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {/* Subtle grid line */}
          <line
            x1={padX}
            y1={height - padY}
            x2={width - padX}
            y2={height - padY}
            stroke="currentColor"
            strokeOpacity="0.1"
            strokeDasharray="2,2"
          />
          {/* Views line */}
          <path
            d={viewsD}
            fill="none"
            stroke="#8b5cf6"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="opacity-70 dark:opacity-90"
          />
          {/* Reach line */}
          <path
            d={reachD}
            fill="none"
            stroke="#0284c7"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
}

export function InsightsPerformanceCard({
  workspaceId,
  accounts,
  isOwner,
}: InsightsPerformanceCardProps) {
  const { t, i18n } = useTranslation();
  const [range, setRange] = useState<"7d" | "28d">("7d");

  const activeAccounts = accounts.filter((a) => a.status !== "disconnected");
  const [selectedId, setSelectedId] = useState<string | undefined>(activeAccounts[0]?.id);

  const activeAccount = activeAccounts.find((a) => a.id === selectedId) ?? activeAccounts[0];
  const summaryQuery = useInsightsSummary(workspaceId, activeAccount?.id, range);
  const summary = summaryQuery.data;

  if (activeAccounts.length === 0) {
    return null;
  }

  const formatNumber = (num: number | null | undefined) => num == null ? (
    <><span aria-hidden="true">—</span><span className="sr-only">{t("core.unavailable")}</span></>
  ) : new Intl.NumberFormat(i18n.language).format(num);

  return (
    <Card data-testid="insights-performance-card" className="flex flex-col gap-4 bg-surface p-5 border-border/80">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ChartIcon className="text-primary-600 dark:text-primary-400" />
          <h2 className="type-section text-primary">
            {t("home.insights.title")}
          </h2>
          {activeAccount?.is_simulated && <SimulatedBadge />}
        </div>

        <div className="flex items-center gap-2">
          {activeAccounts.length > 1 && (
            <select
              aria-label={t("home.insights.account")}
              value={activeAccount?.id}
              onChange={(e) => setSelectedId(e.target.value)}
              className="rounded-control border border-control bg-surface px-2 py-1 text-xs text-primary"
            >
              {activeAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  @{a.username ?? "instagram"}
                </option>
              ))}
            </select>
          )}

          {/* Range Toggle */}
          <div className="inline-flex rounded-control border border-border bg-surface-subtle p-0.5">
            <button
              type="button"
              onClick={() => setRange("7d")}
              aria-pressed={range === "7d"}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                range === "7d"
                  ? "bg-surface text-primary shadow-2xs font-semibold"
                  : "text-secondary hover:text-primary"
              }`}
            >
              {t("home.insights.range7d")}
            </button>
            <button
              type="button"
              onClick={() => setRange("28d")}
              aria-pressed={range === "28d"}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                range === "28d"
                  ? "bg-surface text-primary shadow-2xs font-semibold"
                  : "text-secondary hover:text-primary"
              }`}
            >
              {t("home.insights.range28d")}
            </button>
          </div>
        </div>
      </div>

      <div>
        {summaryQuery.isPending ? (
          <div className="py-6 text-center text-xs text-stone-500 dark:text-stone-400">
            {t("home.insights.loading")}
          </div>
        ) : summaryQuery.isError ? (
          <div className="py-4 text-center text-xs text-rose-600 dark:text-rose-400">
            {t("home.insights.errorLoading")}
          </div>
        ) : summary?.status === "not_granted" ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/60 dark:bg-amber-950/20">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
                  {t("home.insights.scopeNotGrantedTitle")}
                </p>
                <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-300">
                  {t("home.insights.scopeNotGrantedDesc")}
                </p>
              </div>
              {isOwner && (
                <Link to={`/w/${workspaceId}/more/settings/connections`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control bg-action px-3 py-2 text-xs font-semibold text-on-action hover:bg-action-hover focus-visible:outline-2 focus-visible:outline-focus">
                    <LinkIcon className="h-3.5 w-3.5" />
                    {t("home.insights.reconnectCta")}
                </Link>
              )}
            </div>
          </div>
        ) : summary?.status === "below_threshold" ? (
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-center dark:border-stone-800 dark:bg-stone-900/40">
            <p className="text-xs text-stone-600 dark:text-stone-300">
              {t("home.insights.belowThresholdDesc")}
            </p>
          </div>
        ) : summary?.status === "syncing" ? (
          <div className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-center dark:border-sky-900/50 dark:bg-sky-950/20">
            <p className="text-sm font-medium text-sky-900 dark:text-sky-200">
              {t("home.insights.syncingTitle")}
            </p>
            <p className="mt-0.5 text-xs text-sky-700 dark:text-sky-300">
              {t("home.insights.syncingDesc")}
            </p>
          </div>
        ) : (
          <div>
            {summary?.status === "partial" ? (
              <p role="status" className="mb-3 text-sm text-secondary" data-testid="insights-partial">
                {t("home.insights.partial", { current: summary.current_days_covered, previous: summary.previous_days_covered, days: range === "7d" ? 7 : 28 })}
              </p>
            ) : null}
            {/* 3 Main KPIs */}
            <div className="grid grid-cols-3 gap-3">
              {/* Reach */}
              <div className="rounded-lg border border-stone-200/80 bg-stone-50/60 p-3 dark:border-stone-800 dark:bg-stone-900/40">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    {t("home.insights.reach")}
                  </span>
                  <DeltaPill delta={summary?.reach_delta_pct} range={range} />
                </div>
                <div className="mt-1.5 text-xl font-bold tracking-tight text-stone-900 dark:text-stone-100">
                  {formatNumber(summary?.reach)}
                </div>
                <div className="mt-0.5 text-[11px] text-secondary">
                  {t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
                </div>
              </div>

              {/* Views */}
              <div className="rounded-lg border border-stone-200/80 bg-stone-50/60 p-3 dark:border-stone-800 dark:bg-stone-900/40">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    {t("home.insights.views")}
                  </span>
                  <DeltaPill delta={summary?.views_delta_pct} range={range} />
                </div>
                <div className="mt-1.5 text-xl font-bold tracking-tight text-stone-900 dark:text-stone-100">
                  {formatNumber(summary?.views)}
                </div>
                <div className="mt-0.5 text-[11px] text-secondary">
                  {t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
                </div>
              </div>

              {/* Interactions */}
              <div className="rounded-lg border border-stone-200/80 bg-stone-50/60 p-3 dark:border-stone-800 dark:bg-stone-900/40">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    {t("home.insights.interactions")}
                  </span>
                  <DeltaPill delta={summary?.interactions_delta_pct} range={range} />
                </div>
                <div className="mt-1.5 text-xl font-bold tracking-tight text-stone-900 dark:text-stone-100">
                  {formatNumber(summary?.interactions)}
                </div>
                <div className="mt-0.5 text-[11px] text-secondary">
                  {t("home.insights.vsPrevPeriod", { days: range === "7d" ? 7 : 28 })}
                </div>
              </div>
            </div>

            {/* Sparkline chart */}
            {summary?.sparkline && summary.sparkline.length > 0 && (
              <Sparkline points={summary.sparkline} />
            )}

            {/* Bottom bar with followers & link */}
            <div className="mt-3 flex items-center justify-between border-t border-stone-200/80 pt-2.5 text-xs dark:border-stone-800">
              {summary?.follower_count !== null && summary?.follower_count !== undefined ? (
                <div className="text-stone-600 dark:text-stone-400">
                  <span className="font-medium text-stone-900 dark:text-stone-200">
                    {formatNumber(summary.follower_count)}
                  </span>{" "}
                  {t("home.insights.followersTotal")}
                  {summary.follower_delta !== null && summary.follower_delta !== undefined && (
                    <span className="ml-1 text-emerald-700 dark:text-emerald-400">
                      ({summary.follower_delta >= 0 ? `+${summary.follower_delta}` : summary.follower_delta})
                    </span>
                  )}
                </div>
              ) : (
                <div />
              )}

              <Link
                to={`/w/${workspaceId}/more/reports`}
                className="font-medium text-primary-600 hover:underline dark:text-primary-400"
              >
                {t("home.insights.fullReportsLink")} →
              </Link>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
