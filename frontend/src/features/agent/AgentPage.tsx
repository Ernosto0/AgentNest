import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { newRequestId } from "@/features/commands/hooks";
import { capabilityLabel } from "@/features/content/messages";
import {
  useAgentOverview,
  useAgentPersonality,
  useAgentDelegation,
  useChangeAgent,
  useAgentTasks,
  useSubmitAgentTask,
  actionLabelKey,
} from "./hooks";
import { PersonalityForm } from "./PersonalityForm";
import { DelegationForm } from "./DelegationForm";

export function AgentPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const [params, setParams] = useSearchParams();
  const account =
    accounts.data?.find((a) => a.id === params.get("account")) ??
    accounts.data?.find((a) => a.status !== "disconnected");

  return (
    <div className="flex min-w-0 flex-col gap-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("agent.title")}</h1>
      </div>
      {accounts.error ? <ErrorMessage error={accounts.error} /> : null}
      {accounts.data?.length ? (
        <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
          <span>{t("agent.account")}</span>
          <select
            className="w-full sm:w-80 rounded-control border border-border bg-surface px-3 py-2 text-base text-primary shadow-xs focus-visible:outline-2 focus-visible:outline-focus"
            value={account?.id ?? ""}
            onChange={(e) => setParams({ account: e.target.value })}
          >
            {accounts.data.map((a) => (
              <option key={a.id} value={a.id}>
                @{a.username ?? t("agent.account")}
              </option>
            ))}
          </select>
        </label>
      ) : accounts.isPending ? (
        <p role="status" className="text-sm text-secondary">
          {t("common.loading")}
        </p>
      ) : !accounts.error ? (
        <p className="text-sm text-secondary">{t("agent.noAccount")}</p>
      ) : null}
      {account ? (
        <AccountAgent
          key={`${workspace.id}:${account.id}`}
          accountId={account.id}
          connected={account.status === "connected"}
          capabilities={account.capabilities}
        />
      ) : null}
    </div>
  );
}

function AccountAgent({
  accountId,
  connected,
  capabilities,
}: {
  accountId: string;
  connected: boolean;
  capabilities: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const ws = workspace.id;
  const overview = useAgentOverview(ws, accountId);
  const personality = useAgentPersonality(ws, accountId);
  const delegation = useAgentDelegation(ws, accountId);
  const change = useChangeAgent(ws, accountId);
  const tasks = useAgentTasks(ws, accountId);
  const submit = useSubmitAgentTask(ws, accountId);
  const [text, setText] = useState("");
  const [requestId, setRequestId] = useState(newRequestId);
  const [confirm, setConfirm] = useState(false);
  const owner = role === "owner";
  const data = overview.data;

  return (
    <>
      {overview.error ? <ErrorMessage error={overview.error} /> : null}
      {data ? (
        <>
          <Card className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.overview")}</h2>
                <span className="inline-flex items-center rounded-control bg-surface-subtle px-2.5 py-0.5 text-xs font-semibold text-primary border border-border">
                  {t(`agent.controller.${data.controller_mode}`)}
                </span>
                <span className={`inline-flex items-center rounded-control px-2.5 py-0.5 text-xs font-semibold border border-border ${data.state === "active" ? "bg-success-subtle text-success" : "bg-attention-subtle text-attention"}`}>
                  {t(`agent.states.${data.state}`)}
                </span>
              </div>
              {data.is_simulated ? <SimulatedBadge /> : null}
            </div>
            <p role="status" className="text-sm font-medium text-secondary">
              {t(`agent.controller.${data.controller_mode}`)} | {t(`agent.states.${data.state}`)}
            </p>
            <div className="rounded-panel border border-border bg-surface-subtle p-3.5">
              <p className="text-sm font-medium text-primary">
                {t("agent.waitingCounts", {
                  questions: data.pending_questions,
                  approvals: data.pending_approvals,
                })}
              </p>
              <div className="mt-2 flex flex-wrap gap-4 text-sm">
                <Link className="font-medium text-action hover:text-action-hover underline" to={`/w/${ws}/approvals`}>
                  {t("agent.openApprovals")}
                </Link>
                <Link className="font-medium text-action hover:text-action-hover underline" to={`/w/${ws}/more/agent/questions?account=${accountId}`}>
                  {t("agent.openQuestions")}
                </Link>
                <Link className="font-medium text-action hover:text-action-hover underline" to={`/w/${ws}/more/agent/comments?account=${accountId}`}>
                  {t("agent.openComments")}
                </Link>
              </div>
            </div>
            <ul className="grid grid-cols-2 sm:grid-cols-3 gap-2 rounded-panel border border-border bg-surface-subtle p-3 text-sm text-secondary">
              {Object.entries(data.session_counts).map(([state, count]) => (
                <li key={state} className="flex items-center justify-between gap-1 rounded-control bg-surface px-2.5 py-1.5 border border-border/50">
                  <span>{t(`agent.states.${state}`)}:</span>
                  <span className="font-semibold text-primary">{count}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-attention font-medium bg-attention-subtle/50 p-2.5 rounded-control border border-border">{t("agent.pauseWarning")}</p>
            {!connected ? (
              <p role="status" className="rounded-panel border border-border bg-danger-subtle p-3.5 text-sm font-medium text-danger">
                {t("agent.connectionRequired")}
              </p>
            ) : null}
            <Link className="text-sm font-medium text-action hover:text-action-hover underline" to={`/w/${ws}/more/settings/connections`}>
              {t("automation.manageConnection")}
            </Link>
            {owner ? (
              <div className="flex flex-wrap gap-2.5 pt-2 border-t border-border">
                {data.controller_mode === "legacy" ? (
                  <Button disabled={!connected || change.isPending} onClick={() => setConfirm(true)}>
                    {t("agent.enable")}
                  </Button>
                ) : (
                  <>
                    <Button
                      disabled={change.isPending || (data.state === "paused" && !connected)}
                      onClick={() =>
                        change.mutate({
                          command: data.state === "active" ? "pause" : "resume",
                          version: data.config_version,
                          requestId: newRequestId(),
                        })
                      }
                    >
                      {t(data.state === "active" ? "agent.pause" : "agent.resume")}
                    </Button>
                    <Button variant="secondary" disabled={change.isPending} onClick={() => setConfirm(true)}>
                      {t("agent.returnLegacy")}
                    </Button>
                  </>
                )}
              </div>
            ) : (
              <p className="text-sm text-secondary font-medium">{t("agent.ownerOnly")}</p>
            )}
            {confirm ? (
              <div className="rounded-panel border border-border bg-attention-subtle p-4 flex flex-col gap-3 shadow-xs">
                <p className="text-sm text-attention font-medium">{t("agent.migrationWarning")}</p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    disabled={change.isPending}
                    onClick={() =>
                      change.mutate(
                        {
                          command: "activate",
                          version: data.config_version,
                          requestId: newRequestId(),
                          mode: data.controller_mode === "legacy" ? "agent" : "legacy",
                        },
                        { onSuccess: () => setConfirm(false) },
                      )
                    }
                  >
                    {t("agent.confirmController")}
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>
                    {t("common.cancel")}
                  </Button>
                </div>
              </div>
            ) : null}
            {change.error ? <ErrorMessage error={change.error} /> : null}
          </Card>

          <Card className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs">
            <div className="border-b border-border pb-3">
              <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.capabilities")}</h2>
            </div>
            <p className="text-sm text-secondary">{t("agent.capabilityHint")}</p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-sm pt-1">
              {Object.entries(capabilities).map(([name, allowed]) => (
                <li key={name} className="flex items-center justify-between rounded-control border border-border bg-surface-subtle px-3 py-2.5 shadow-xs">
                  <span className="text-primary font-medium">
                    {name === "comment_reply"
                      ? t("agent.actions.comment_reply")
                      : name === "comment_private_reply"
                        ? t("agent.actions.comment_private_reply")
                        : name === "comment_moderate"
                          ? t("agent.moderateCapability")
                          : capabilityLabel(name, t)}
                  </span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-control border border-border ${allowed === true ? "text-success bg-success-subtle" : "text-secondary bg-surface"}`}>
                    {t(allowed === true ? "agent.available" : "agent.unavailable")}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          {personality.data ? (
            <PersonalityForm
              key={`persona:${accountId}`}
              ws={ws}
              account={accountId}
              data={personality.data}
              editable={role !== "staff"}
            />
          ) : null}
          {personality.error ? <ErrorMessage error={personality.error} /> : null}

          {delegation.isSuccess ? (
            <DelegationForm
              key={`policy:${data.config_version}:${delegation.data?.version ?? 0}`}
              ws={ws}
              account={accountId}
              config={data.config_version}
              data={delegation.data ?? null}
              owner={owner}
            />
          ) : null}
          {delegation.error ? <ErrorMessage error={delegation.error} /> : null}

          <Card className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
            <div className="border-b border-border pb-3">
              <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.tasks")}</h2>
            </div>
            <p className="text-sm text-secondary">{t("agent.taskHint")}</p>
            <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
              <span className="text-primary">{t("agent.taskText")}</span>
              <textarea
                className="w-full rounded-control border border-border bg-surface p-3 text-base text-primary placeholder:text-secondary focus-visible:outline-2 focus-visible:outline-focus focus:border-control"
                rows={3}
                value={text}
                maxLength={4000}
                disabled={submit.isPending}
                onChange={(e) => {
                  setText(e.target.value);
                  setRequestId(newRequestId());
                }}
              />
            </label>
            <div>
              <Button
                disabled={
                  submit.isPending ||
                  !text.trim() ||
                  !connected ||
                  data.controller_mode !== "agent" ||
                  data.state !== "active"
                }
                onClick={() =>
                  submit.mutate(
                    { text, client_request_id: requestId },
                    {
                      onSuccess: () => {
                        setText("");
                        setRequestId(newRequestId());
                      },
                    },
                  )
                }
              >
                {t("agent.submitTask")}
              </Button>
            </div>
            {submit.error ? <ErrorMessage error={submit.error} /> : null}
            {submit.isSuccess ? (
              <p role="status" className="rounded-control bg-success-subtle p-2.5 text-sm font-medium text-success border border-border">
                {t("agent.taskAccepted")}
              </p>
            ) : null}
            {tasks.error ? <ErrorMessage error={tasks.error} /> : null}
            <ul className="flex flex-col gap-3">
              {tasks.data?.items.map((task) => (
                <li key={task.id} className="rounded-panel border border-border bg-surface-subtle p-4 shadow-xs flex flex-col gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
                    <Link className="font-semibold text-action hover:text-action-hover underline" to={`/w/${ws}/more/agent/tasks/${task.id}?account=${accountId}`}>
                      {t("agent.taskProgress")}
                    </Link>
                    <span className="inline-flex items-center rounded-control bg-surface px-2.5 py-0.5 text-xs font-semibold text-primary border border-border">
                      {t(`agent.states.${task.status}`, { defaultValue: t("agent.pending") })}
                    </span>
                  </div>
                  {task.actions.map((action) => (
                    <div key={action.action_id} className="flex flex-wrap items-center gap-2 text-sm text-secondary">
                      <span>{t(actionLabelKey(action.action_type))}:</span>
                      <span className="font-medium text-primary">
                        {t(`agent.states.${action.status}`, { defaultValue: t("agent.pending") })}
                      </span>
                      {action.is_simulated ? <SimulatedBadge /> : null}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
            {tasks.data?.next_cursor ? (
              <p className="text-xs text-secondary">{t("agent.recentTasksOnly")}</p>
            ) : null}
          </Card>

          <Card className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs">
            <div className="border-b border-border pb-3">
              <h2 className="text-lg font-heading font-semibold text-primary">{t("agent.recentActions")}</h2>
            </div>
            <p className="text-sm text-secondary">{t("agent.outcomeHint")}</p>
            <ul className="mt-1 flex flex-col gap-2">
              {data.recent_actions.map((action) => (
                <li key={action.id} className="flex flex-wrap items-center justify-between rounded-control border border-border bg-surface-subtle px-3 py-2.5 text-sm shadow-xs">
                  <span className="font-medium text-primary">{t(actionLabelKey(action.action_type))}</span>
                  <span className="inline-flex items-center rounded-control bg-surface px-2 py-0.5 text-xs font-medium text-secondary border border-border">
                    {t(`agent.states.${action.status}`, { defaultValue: t("agent.pending") })}
                  </span>
                </li>
              ))}
            </ul>
            {!data.recent_actions.length ? (
              <p className="text-sm text-secondary">{t("agent.noActions")}</p>
            ) : null}
          </Card>
          {data.controller_mode === "legacy" ? (
            <Link className="text-sm font-medium text-action hover:text-action-hover underline" to={`/w/${ws}/more/automation`}>
              {t("agent.legacySettings")}
            </Link>
          ) : null}
        </>
      ) : null}
    </>
  );
}
