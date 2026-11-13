import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, LayersIcon } from "@/components/icons";
import { PageHeader } from "@/components/Layout";
import { SkeletonRows } from "@/features/home/DashboardPanel";
import { isLocalDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ActivityFilters } from "./ActivityFilters";
import { ActivitySummaryStrip } from "./ActivitySummaryStrip";
import { ActivityTimeline } from "./ActivityTimeline";
import { isActivityGroup, isOutcome, useActivity, useActivitySummary, type ActivityFilters as Filters } from "./hooks";
import { buildTimeline } from "./timeline";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Filters live in the URL so a view can be shared, reloaded and navigated back to. */
function readFilters(params: URLSearchParams): Filters {
  const type = params.get("type");
  const level = params.get("level");
  const day = params.get("day");
  const flow = params.get("flow");
  return {
    group: isActivityGroup(type) ? type : null,
    outcome: isOutcome(level) ? level : null,
    day: isLocalDay(day) ? day : null,
    technical: params.get("technical") === "1",
    flow: flow && UUID.test(flow) ? flow : null,
  };
}

function writeFilters(filters: Filters): Record<string, string> {
  const out: Record<string, string> = {};
  if (filters.flow) return { flow: filters.flow };
  if (filters.group) out.type = filters.group;
  if (filters.outcome) out.level = filters.outcome;
  if (filters.day) out.day = filters.day;
  if (filters.technical) out.technical = "1";
  return out;
}

/**
 * Activity (J5, ui-spec §4.13): what happened in the workspace, as a timeline of local days.
 *
 * The server classifies every audit entry (level, routine, grouping key) and filters in SQL; this
 * page only arranges what it receives. Grouping folds adjacent entries of the same kind into one
 * row that expands to every individual entry, so nothing in the audit log is hidden or merged
 * away. Routine bookkeeping is left out by default and one switch brings it back.
 */
export function ActivityFeed() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const feed = useActivity(workspace.id, filters);
  const summary = useActivitySummary(workspace.id);
  const today = todayIn(workspace.timezone);

  const entries = useMemo(() => feed.data?.pages.flatMap((page) => page.items) ?? [], [feed.data]);
  const sections = useMemo(
    () => buildTimeline(entries, workspace.timezone, Boolean(feed.hasNextPage)),
    [entries, workspace.timezone, feed.hasNextPage],
  );

  const apply = (next: Filters) => setParams(writeFilters(next), { replace: false });
  const change = (patch: Partial<Filters>) => apply({ ...filters, ...patch, flow: null });
  const clear = () => apply({ group: null, outcome: null, day: null, technical: filters.technical, flow: null });
  const showFlow = (flow: string) => {
    apply({ ...filters, flow });
    const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo?.({ top: 0, behavior: reduced ? "auto" : "smooth" });
  };

  const narrowed = filters.group !== null || filters.outcome !== null || filters.day !== null;
  const loadedAll = feed.isSuccess && !feed.hasNextPage;

  return (
    <div className="flex w-full min-w-0 flex-col gap-5 lg:gap-6">
      <PageHeader title={t("activity.title")} description={t("activity.intro")} />

      {filters.flow ? (
        <div role="status" data-testid="activity-flow" className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl bg-info-subtle px-4 py-3 sm:px-5">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface text-base text-info">
            <LayersIcon />
          </span>
          <div className="min-w-0 flex-1 basis-56">
            <p className="text-body font-semibold text-primary">{t("activity.flow.title")}</p>
            <p className="text-metadata text-secondary">{t("activity.flow.hint")}</p>
          </div>
          <Button variant="secondary" onClick={() => apply({ ...filters, flow: null })}>
            {t("activity.flow.back")}
          </Button>
        </div>
      ) : (
        <>
          <ActivitySummaryStrip
            summary={summary.data}
            pending={summary.isPending}
            failed={summary.isError}
            outcome={filters.outcome}
            onOutcome={(outcome) => change({ outcome })}
          />
          <ActivityFilters filters={filters} today={today} onChange={change} onClear={clear} />
        </>
      )}

      {feed.isError && !feed.data ? <ErrorMessage error={feed.error} /> : null}

      {feed.isPending ? (
        <div className="rounded-2xl border border-border bg-surface px-5 py-4">
          <SkeletonRows label={t("common.loading")} rows={6} />
        </div>
      ) : null}

      {feed.isSuccess && entries.length === 0 ? (
        narrowed || filters.flow ? (
          <EmptyState
            icon={<ClockIcon />}
            title={t("activity.filteredEmpty")}
            description={filters.technical ? t("activity.filteredEmptyHint") : t("activity.filteredEmptyTechnical")}
            action={
              <Button variant="secondary" onClick={clear}>
                {t("activity.filters.clear")}
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<ClockIcon />}
            title={t("activity.empty")}
            description={filters.technical ? t("activity.emptyHint") : t("activity.emptyKeyHint")}
            action={
              filters.technical ? undefined : (
                <Button variant="secondary" onClick={() => change({ technical: true })}>
                  {t("activity.showTechnical")}
                </Button>
              )
            }
          />
        )
      ) : null}

      {entries.length > 0 ? (
        <ActivityTimeline sections={sections} clock={{ timezone: workspace.timezone, today }} onShowFlow={filters.flow ? null : showFlow} />
      ) : null}

      {entries.length > 0 ? (
        <div className="flex min-w-0 flex-col items-center gap-3 pt-1 pb-2 text-center lg:ml-[calc(9.5rem+1.5rem)]">
          <p role="status" className="text-metadata text-secondary">
            {loadedAll ? t("activity.endOfHistory", { count: entries.length }) : t("activity.loaded", { count: entries.length })}
          </p>
          {feed.isFetchNextPageError ? <ErrorMessage error={feed.error} /> : null}
          {feed.hasNextPage ? (
            <Button variant="secondary" pending={feed.isFetchingNextPage} onClick={() => void feed.fetchNextPage()}>
              {feed.isFetchingNextPage ? t("common.loading") : feed.isFetchNextPageError ? t("activity.retry") : t("activity.loadMore")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
