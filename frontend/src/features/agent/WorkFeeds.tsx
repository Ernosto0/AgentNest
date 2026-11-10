import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRightIcon, HandIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, StatePill, StateTile } from "./AgentParts";
import { actionLabelKey, type Schema } from "./hooks";
import { ACTION_ICON, TONE_PILL, absoluteTime, actionSurface, clockTime, relativeTime, stateTone } from "./presentation";


type Task = Schema<"TaskOut">;
type Action = Schema<"OverviewAction">;

/**
 * One owner request. The API returns no request text (body-free list), so a request is named by
 * what it led to (its first action) and when it was sent; the status is the latest run's status.
 */
export function TaskRow({
  task,
  accountId,
  highlight = false,
  timeStyle = "relative",
}: {
  task: Task;
  accountId: string;
  highlight?: boolean;
  timeStyle?: "relative" | "clock";
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ws = workspace.id;
  const first = task.actions[0];
  const title = first
    ? task.actions.length > 1
      ? t("agent.request.titleMore", { action: t(actionLabelKey(first.action_type)), count: task.actions.length - 1 })
      : t(actionLabelKey(first.action_type))
    : t("agent.request.title");
  const simulated = task.actions.some((a) => a.is_simulated);
  const absolute = absoluteTime(task.created_at, i18n.language, workspace.timezone);
  const when = timeStyle === "clock" ? clockTime(task.created_at, i18n.language, workspace.timezone) : relativeTime(task.created_at, i18n.language);
  const href = `/w/${ws}/more/agent/tasks/${task.id}?account=${accountId}`;
  // With one action the title already names it, so only its result is listed.
  const single = task.actions.length === 1;

  return (
    <li
      data-testid={`task-${task.id}`}
      className={`flex min-w-0 gap-3 rounded-xl px-2 py-3 transition-colors sm:px-3 ${highlight ? "bg-success-subtle/60 ring-1 ring-success/30" : "hover:bg-surface-subtle/60"}`}
    >
      <StateTile state={task.clarification ? "waiting_clarification" : task.status} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <Link
            to={href}
            className={`group/title inline-flex min-w-0 items-center gap-0.5 rounded-sm text-body font-semibold text-primary [overflow-wrap:anywhere] hover:text-action ${FOCUS}`}
          >
            <span className="underline-offset-2 group-hover/title:underline">{title}</span>
            <span className="sr-only">, {absolute}</span>
            <ChevronRightIcon aria-hidden="true" className="shrink-0 text-secondary group-hover/title:text-action" />
          </Link>
          <StatePill state={task.status} />
          {simulated ? <SimulatedBadge compact /> : null}
        </div>
        <p className="text-xs text-secondary">
          <time dateTime={task.created_at} title={absolute}>{t("agent.request.sent", { time: when })}</time>
          {task.source_channel === "telegram" ? <span> · {t("agent.request.viaTelegram")}</span> : null}
        </p>

        {task.clarification ? (
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-attention-subtle px-3 py-2">
            <HandIcon aria-hidden="true" className="shrink-0 text-attention" />
            <p className="min-w-0 flex-1 basis-48 text-metadata text-primary">
              <span className="font-semibold">{t("agent.request.asks")} </span>
              <span className="line-clamp-2 [overflow-wrap:anywhere]">{task.clarification}</span>
            </p>
            <Link to={href} className={`inline-flex min-h-9 items-center rounded-sm text-metadata font-semibold text-attention underline underline-offset-2 ${FOCUS}`}>
              {t("agent.request.answer")}
            </Link>
          </div>
        ) : null}

        {task.actions.length > 0 ? (
          <ul className="flex min-w-0 flex-col gap-1">
            {task.actions.map((action) => {
              const Icon = ACTION_ICON[actionSurface(action.action_type)] ?? SparkIcon;
              const state = action.content_status ?? action.status;
              return (
                <li key={action.action_id} className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-metadata">
                  {single ? (
                    <span className="text-secondary">{t("agent.request.result")}</span>
                  ) : (
                    <>
                      <Icon aria-hidden="true" className="shrink-0 text-secondary" />
                      <span className="text-primary">{t(actionLabelKey(action.action_type))}</span>
                    </>
                  )}
                  <StatePill state={state} />
                  {action.approval_id ? (
                    <Link to={`/w/${ws}/approvals`} className={`rounded-sm text-xs font-semibold text-action hover:underline ${FOCUS}`}>
                      {t("agentWork.approvals")}
                    </Link>
                  ) : null}
                  {action.content_id ? (
                    <Link to={`/w/${ws}/content/${action.content_id}`} className={`rounded-sm text-xs font-semibold text-action hover:underline ${FOCUS}`}>
                      {t("agentWork.openContent")}
                    </Link>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </li>
  );
}

/**
 * One recorded agent action. Status words come from the server state; "succeeded" is the only
 * completion. When the action came from one of the owner's own requests, that request is linked.
 * Overview actions carry no per-item simulation flag; the section shows the account's badge.
 */
export function ActionRow({
  action,
  taskId,
  accountId,
  timeStyle = "relative",
}: {
  action: Action;
  taskId?: string;
  accountId: string;
  timeStyle?: "relative" | "clock";
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const Icon = ACTION_ICON[actionSurface(action.action_type)] ?? SparkIcon;
  const absolute = absoluteTime(action.created_at, i18n.language, workspace.timezone);
  const when = timeStyle === "clock" ? clockTime(action.created_at, i18n.language, workspace.timezone) : relativeTime(action.created_at, i18n.language);
  return (
    <li data-testid={`action-${action.id}`} className="relative flex min-w-0 items-start gap-3 py-2.5">
      <span aria-hidden="true" className={`relative z-10 flex size-8 shrink-0 items-center justify-center rounded-lg text-base ring-4 ring-surface ${TONE_PILL[stateTone(action.status)]}`}>
        <Icon />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <p className="min-w-0 text-body font-medium text-primary">{t(actionLabelKey(action.action_type))}</p>
          <StatePill state={action.status} />
        </div>
        <p className="text-xs text-secondary">
          <time dateTime={action.created_at} title={absolute}>{when}</time>
          {taskId ? (
            <>
              {" · "}
              <Link to={`/w/${workspace.id}/more/agent/tasks/${taskId}?account=${accountId}`} className={`rounded-sm font-semibold text-action hover:underline ${FOCUS}`}>
                {t("agent.actionsFeed.fromRequest")}
              </Link>
            </>
          ) : null}
        </p>
      </div>
    </li>
  );
}

/** A vertical rule behind the icon column turns a list of actions into a timeline. */
export function Timeline({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <ol aria-label={label} className="relative flex min-w-0 flex-col before:absolute before:top-4 before:bottom-4 before:left-4 before:w-px before:-translate-x-1/2 before:bg-border">
      {children}
    </ol>
  );
}
