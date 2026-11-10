import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { SocialAccount } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, InboxIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { PanelLink, SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AssistantHero } from "./AssistantHero";
import { SectionTitle, Surface } from "./AgentParts";
import type { Schema } from "./hooks";
import { RequestComposer } from "./RequestComposer";
import { CalendarPanel, CapabilitiesPanel, ControlPanel } from "./SidePanels";
import { taskByAction } from "./presentation";
import { ActionRow, TaskRow, Timeline } from "./WorkFeeds";

const REQUESTS_SHOWN = 5;
const ACTIONS_SHOWN = 5;
const CLOSED = new Set(["completed", "failed", "cancelled"]);

/**
 * Overview, top to bottom: the assistant (identity, state, control, what waits on you), then two
 * independent columns. The main column is where the owner directs and follows work (ask, requests,
 * recent actions); the side column is what the assistant can use (capabilities, calendar, control).
 */
export function OverviewPanel({
  account,
  data,
  owner,
  tasks,
  policy,
  panelHref,
  picker,
}: {
  account: SocialAccount;
  data: Schema<"AgentOverview">;
  owner: boolean;
  tasks: { data?: Schema<"Page_TaskOut_">; error: Error | null; isPending: boolean };
  policy: Schema<"DelegationPolicy"> | null | undefined;
  panelHref: (panel: string) => string;
  picker?: ReactNode;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ws = workspace.id;
  const [submitted, setSubmitted] = useState<string | null>(null);
  const connected = account.status === "connected";
  const items = tasks.data?.items ?? [];
  const open = items.filter((task) => !CLOSED.has(task.status) || task.clarification);
  const ordered = [...open, ...items.filter((task) => !open.includes(task))];
  const shown = ordered.slice(0, REQUESTS_SHOWN);
  const owners = taskByAction(items);
  const actions = data.recent_actions.slice(0, ACTIONS_SHOWN);

  return (
    <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
      <AssistantHero account={account} data={data} owner={owner} picker={picker} />

      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
          <RequestComposer ws={ws} accountId={account.id} data={data} connected={connected} onSubmitted={setSubmitted} />

          <Surface aria-labelledby="agent-requests-title" data-testid="agent-requests" className="gap-2 p-4 sm:p-5">
            <SectionTitle
              id="agent-requests-title"
              icon={<InboxIcon />}
              title={t("agent.tasks")}
              meta={tasks.data && items.length ? t("agent.requests.meta", { open: open.length, count: items.length }) : undefined}
              action={items.length > REQUESTS_SHOWN ? <PanelLink to={panelHref("history")}>{t("agent.requests.all")}</PanelLink> : undefined}
            />
            {tasks.error ? (
              <ErrorMessage error={tasks.error} />
            ) : tasks.isPending ? (
              <SkeletonRows label={t("common.loading")} rows={2} />
            ) : items.length === 0 ? (
              <p className="rounded-xl bg-surface-subtle/70 px-3.5 py-3 text-metadata text-secondary">{t("agent.requests.empty")}</p>
            ) : (
              <ul className="-mx-2 flex flex-col divide-y divide-border/70 sm:-mx-3">
                {shown.map((task) => (
                  <TaskRow key={task.id} task={task} accountId={account.id} highlight={task.id === submitted} />
                ))}
              </ul>
            )}
            {items.length > REQUESTS_SHOWN ? (
              <p className="text-xs text-secondary">{t("agent.requests.more", { shown: shown.length, count: items.length })}</p>
            ) : null}
          </Surface>

          <Surface aria-labelledby="agent-actions-title" data-testid="agent-actions" className="gap-2 p-4 sm:p-5">
            <SectionTitle
              id="agent-actions-title"
              icon={<ClockIcon />}
              title={t("agent.recentActions")}
              meta={
                <span className="inline-flex flex-wrap items-center gap-1.5">
                  {t("agent.outcomeHint")}
                  {data.is_simulated && actions.length ? <SimulatedBadge compact /> : null}
                </span>
              }
              action={data.recent_actions.length ? <PanelLink to={panelHref("history")}>{t("agent.actionsFeed.all")}</PanelLink> : undefined}
            />
            {actions.length === 0 ? (
              <p className="rounded-xl bg-surface-subtle/70 px-3.5 py-3 text-metadata text-secondary">{t("agent.noActions")}</p>
            ) : (
              <Timeline>
                {actions.map((action) => (
                  <ActionRow key={action.id} action={action} taskId={owners.get(action.id)} accountId={account.id} />
                ))}
              </Timeline>
            )}
          </Surface>
        </div>

        <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
          <CapabilitiesPanel
            capabilities={account.capabilities}
            policy={policy}
            permissionsHref={panelHref("permissions")}
            commentsHref={`/w/${ws}/more/agent/comments?account=${account.id}`}
          />
          <CalendarPanel policy={policy} permissionsHref={panelHref("permissions")} />
          <ControlPanel account={account} data={data} owner={owner} />
        </div>
      </div>
    </div>
  );
}
