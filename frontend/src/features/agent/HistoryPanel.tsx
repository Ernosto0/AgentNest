import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { PanelLink, SkeletonRows } from "@/features/home/DashboardPanel";
import { shiftDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { DayLabel, FOCUS, SectionTitle, Surface } from "./AgentParts";
import type { Schema } from "./hooks";
import { CATEGORIES, groupByDay, stateCategory, type Category } from "./presentation";
import { taskByAction } from "./presentation";
import { ActionRow, TaskRow, Timeline } from "./WorkFeeds";

type Task = Schema<"TaskOut">;
type Filter = Category | "all";

const taskCategory = (task: Task): Category => (task.clarification ? "needs_you" : stateCategory(task.status));

/**
 * Deeper inspection than Overview: every loaded request and recorded action, grouped by day on the
 * workspace clock, filterable by what they need. Totals are of what is loaded, never more.
 */
export function HistoryPanel({
  data,
  tasks,
  accountId,
}: {
  data: Schema<"AgentOverview">;
  tasks: { data?: Schema<"Page_TaskOut_">; error: Error | null; isPending: boolean };
  accountId: string;
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const [filter, setFilter] = useState<Filter>("all");
  const items = tasks.data?.items ?? [];
  const actions = data.recent_actions;
  const owners = taskByAction(items);
  const today = todayIn(workspace.timezone);
  const yesterday = shiftDay(today, -1);

  const count = (category: Category) =>
    items.filter((task) => taskCategory(task) === category).length + actions.filter((a) => stateCategory(a.status) === category).length;
  const shownTasks = filter === "all" ? items : items.filter((task) => taskCategory(task) === filter);
  const shownActions = filter === "all" ? actions : actions.filter((a) => stateCategory(a.status) === filter);
  const filters: Filter[] = ["all", ...CATEGORIES.filter((c) => count(c) > 0 || c === filter)];
  const nothing = !tasks.isPending && shownTasks.length === 0 && shownActions.length === 0;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div role="group" aria-label={t("agent.history.filterLabel")} className="flex min-w-0 flex-wrap items-center gap-2">
        {filters.map((name) => {
          const n = name === "all" ? items.length + actions.length : count(name);
          const current = filter === name;
          return (
            <button
              key={name}
              type="button"
              aria-pressed={current}
              onClick={() => setFilter(name)}
              className={`inline-flex min-h-10 items-center gap-2 rounded-full px-3.5 text-metadata font-semibold transition-colors pointer-coarse:min-h-11 ${FOCUS} ${
                current ? "bg-action text-on-action" : "bg-surface text-primary ring-1 ring-border ring-inset hover:bg-surface-subtle"
              }`}
            >
              {t(`agent.history.filter.${name}`)}
              <span className={`min-w-5 rounded-full px-1.5 text-center text-xs leading-5 tabular-nums ${current ? "bg-on-action/20" : "bg-surface-subtle text-secondary"}`}>
                {n}
              </span>
            </button>
          );
        })}
      </div>

      {nothing && filter !== "all" ? (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-border bg-surface px-4 py-3">
          <p className="text-body text-secondary">{t("agent.history.noMatch")}</p>
          <Button variant="secondary" onClick={() => setFilter("all")} className="min-h-10">
            {t("agent.history.showAll")}
          </Button>
        </div>
      ) : null}

      <div className="grid min-w-0 items-start gap-4 lg:gap-5 xl:grid-cols-2">
        <Surface aria-labelledby="agent-history-requests" className="gap-3 p-4 sm:p-5">
          <SectionTitle
            id="agent-history-requests"
            icon={<SparkIcon />}
            title={t("agent.tasks")}
            meta={tasks.data?.next_cursor ? t("agent.recentTasksOnly") : t("agent.history.requestsMeta")}
          />
          {tasks.error ? (
            <ErrorMessage error={tasks.error} />
          ) : tasks.isPending ? (
            <SkeletonRows label={t("common.loading")} rows={3} />
          ) : items.length === 0 ? (
            <p className="rounded-xl bg-surface-subtle/70 px-3.5 py-3 text-metadata text-secondary">{t("agent.requests.empty")}</p>
          ) : shownTasks.length === 0 ? (
            <p className="px-1 text-metadata text-secondary">{t("agent.history.noneInFilter")}</p>
          ) : (
            <div className="flex flex-col gap-3">
              {groupByDay(shownTasks, (task) => task.created_at, workspace.timezone).map((group) => (
                <div key={group.day} className="flex flex-col gap-0.5">
                  <DayLabel day={group.day} today={today} yesterday={yesterday} />
                  <ul className="-mx-2 flex flex-col divide-y divide-border/70 sm:-mx-3">
                    {group.items.map((task) => (
                      <TaskRow key={task.id} task={task} accountId={accountId} timeStyle="clock" />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Surface>

        <Surface aria-labelledby="agent-history-actions" className="gap-3 p-4 sm:p-5">
          <SectionTitle
            id="agent-history-actions"
            icon={<ClockIcon />}
            title={t("agent.recentActions")}
            meta={
              <span className="inline-flex flex-wrap items-center gap-1.5">
                {t("agent.history.actionsMeta", { count: actions.length })}
                {data.is_simulated && actions.length ? <SimulatedBadge compact /> : null}
              </span>
            }
            action={role !== "staff" ? <PanelLink to={`/w/${workspace.id}/more/activity`}>{t("agent.history.activityLog")}</PanelLink> : undefined}
          />
          <p className="text-xs text-secondary">{t("agent.outcomeHint")}</p>
          {actions.length === 0 ? (
            <p className="rounded-xl bg-surface-subtle/70 px-3.5 py-3 text-metadata text-secondary">{t("agent.noActions")}</p>
          ) : shownActions.length === 0 ? (
            <p className="px-1 text-metadata text-secondary">{t("agent.history.noneInFilter")}</p>
          ) : (
            <div className="flex flex-col gap-3">
              {groupByDay(shownActions, (a) => a.created_at, workspace.timezone).map((group) => (
                <div key={group.day} className="flex flex-col gap-0.5">
                  <DayLabel day={group.day} today={today} yesterday={yesterday} />
                  <Timeline>
                    {group.items.map((action) => (
                      <ActionRow key={action.id} action={action} taskId={owners.get(action.id)} accountId={accountId} timeStyle="clock" />
                    ))}
                  </Timeline>
                </div>
              ))}
            </div>
          )}
        </Surface>
      </div>
    </div>
  );
}
