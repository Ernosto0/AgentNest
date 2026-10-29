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
import { useAgentOverview, useAgentPersonality, useAgentDelegation, useChangeAgent, useAgentTasks, useSubmitAgentTask, actionLabelKey } from "./hooks";
import { PersonalityForm, FIELD } from "./PersonalityForm";
import { DelegationForm } from "./DelegationForm";
export function AgentPage() {
    const { t } = useTranslation();
    const { workspace } = useCurrentWorkspace();
    const accounts = useSocialAccounts(workspace.id);
    const [params, setParams] = useSearchParams();
    const account = accounts.data?.find(a => a.id === params.get("account")) ?? accounts.data?.find(a => a.status !== "disconnected");
    return <div className="flex min-w-0 flex-col gap-5"><h1 className="text-2xl font-semibold">{t("agent.title")}</h1>
    {accounts.error ? <ErrorMessage error={accounts.error}/> : null}
    {accounts.data?.length ? <label>{t("agent.account")}<select className={FIELD} value={account?.id ?? ""} onChange={e => setParams({ account: e.target.value })}>{accounts.data.map(a => <option key={a.id} value={a.id}>@{a.username ?? t("agent.account")}</option>)}</select></label> : accounts.isPending ? <p role="status">{t("common.loading")}</p> : !accounts.error ? <p>{t("agent.noAccount")}</p> : null}
    {account ? <AccountAgent key={`${workspace.id}:${account.id}`} accountId={account.id} connected={account.status === "connected"} capabilities={account.capabilities}/> : null}
  </div>;
}
function AccountAgent({ accountId, connected, capabilities }: {
    accountId: string;
    connected: boolean;
    capabilities: Record<string, unknown>;
}) {
    const { t } = useTranslation();
    const { workspace, role } = useCurrentWorkspace();
    const ws = workspace.id;
    const overview = useAgentOverview(ws, accountId), personality = useAgentPersonality(ws, accountId), delegation = useAgentDelegation(ws, accountId);
    const change = useChangeAgent(ws, accountId), tasks = useAgentTasks(ws, accountId), submit = useSubmitAgentTask(ws, accountId);
    const [text, setText] = useState("");
    const [requestId, setRequestId] = useState(newRequestId);
    const [confirm, setConfirm] = useState(false);
    const owner = role === "owner";
    const data = overview.data;
    return <>{overview.error ? <ErrorMessage error={overview.error}/> : null}{data ? <>
    <Card className="flex flex-col gap-3"><h2 className="text-lg font-semibold">{t("agent.overview")}</h2>{data.is_simulated ? <SimulatedBadge /> : null}
      <p role="status">{t(`agent.controller.${data.controller_mode}`)} | {t(`agent.states.${data.state}`)}</p>
      <p>{t("agent.waitingCounts", { questions: data.pending_questions, approvals: data.pending_approvals })}</p>
      <Link className="font-semibold text-indigo-700 underline" to={`/w/${ws}/approvals`}>{t("agent.openApprovals")}</Link>
      <div className="flex flex-wrap gap-3"><Link className="text-indigo-700 underline" to={`/w/${ws}/more/agent/questions?account=${accountId}`}>{t("agent.openQuestions")}</Link><Link className="text-indigo-700 underline" to={`/w/${ws}/more/agent/comments?account=${accountId}`}>{t("agent.openComments")}</Link></div>
      <ul>{Object.entries(data.session_counts).map(([state, count]) => <li key={state}>{t(`agent.states.${state}`)}: {count}</li>)}</ul>
      <p className="text-sm text-amber-900">{t("agent.pauseWarning")}</p>
      {!connected ? <p role="status">{t("agent.connectionRequired")}</p> : null}
      <Link className="text-indigo-700 underline" to={`/w/${ws}/more/settings/connections`}>{t("automation.manageConnection")}</Link>
      {owner ? <div className="flex flex-wrap gap-2">{data.controller_mode === "legacy" ? <Button disabled={!connected || change.isPending} onClick={() => setConfirm(true)}>{t("agent.enable")}</Button> : <><Button disabled={change.isPending || (data.state === "paused" && !connected)} onClick={() => change.mutate({ command: data.state === "active" ? "pause" : "resume", version: data.config_version, requestId: newRequestId() })}>{t(data.state === "active" ? "agent.pause" : "agent.resume")}</Button><Button variant="secondary" disabled={change.isPending} onClick={() => setConfirm(true)}>{t("agent.returnLegacy")}</Button></>}</div> : <p>{t("agent.ownerOnly")}</p>}
      {confirm ? <div className="rounded-lg border border-amber-300 p-3"><p>{t("agent.migrationWarning")}</p><Button disabled={change.isPending} onClick={() => change.mutate({ command: "activate", version: data.config_version, requestId: newRequestId(), mode: data.controller_mode === "legacy" ? "agent" : "legacy" }, { onSuccess: () => setConfirm(false) })}>{t("agent.confirmController")}</Button><Button variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button></div> : null}
      {change.error ? <ErrorMessage error={change.error}/> : null}
    </Card>
    <Card className="flex flex-col gap-2"><h2 className="text-lg font-semibold">{t("agent.capabilities")}</h2><p>{t("agent.capabilityHint")}</p><ul>{Object.entries(capabilities).map(([name, allowed]) => <li key={name}>{name === "comment_reply" ? t("agent.actions.comment_reply") : name === "comment_private_reply" ? t("agent.actions.comment_private_reply") : name === "comment_moderate" ? t("agent.moderateCapability") : capabilityLabel(name, t)}: {t(allowed === true ? "agent.available" : "agent.unavailable")}</li>)}</ul></Card>
    {personality.data ? <PersonalityForm key={`persona:${accountId}`} ws={ws} account={accountId} data={personality.data} editable={role !== "staff"}/> : null}{personality.error ? <ErrorMessage error={personality.error}/> : null}
    {delegation.isSuccess ? <DelegationForm key={`policy:${data.config_version}:${delegation.data?.version ?? 0}`} ws={ws} account={accountId} config={data.config_version} data={delegation.data ?? null} owner={owner}/> : null}{delegation.error ? <ErrorMessage error={delegation.error}/> : null}
    <Card className="flex flex-col gap-3"><h2 className="text-lg font-semibold">{t("agent.tasks")}</h2><p>{t("agent.taskHint")}</p><label>{t("agent.taskText")}<textarea className={FIELD} value={text} maxLength={4000} disabled={submit.isPending} onChange={e => { setText(e.target.value); setRequestId(newRequestId()); }}/></label><Button disabled={submit.isPending || !text.trim() || !connected || data.controller_mode !== "agent" || data.state !== "active"} onClick={() => submit.mutate({ text, client_request_id: requestId }, { onSuccess: () => { setText(""); setRequestId(newRequestId()); } })}>{t("agent.submitTask")}</Button>
      {submit.error ? <ErrorMessage error={submit.error}/> : null}{submit.isSuccess ? <p role="status">{t("agent.taskAccepted")}</p> : null}{tasks.error ? <ErrorMessage error={tasks.error}/> : null}
      <ul className="flex flex-col gap-2">{tasks.data?.items.map(task => <li key={task.id} className="rounded-lg border border-slate-200 p-3"><Link className="text-indigo-700 underline" to={`/w/${ws}/more/agent/tasks/${task.id}?account=${accountId}`}>{t("agent.taskProgress")}: {t(`agent.states.${task.status}`, { defaultValue: t("agent.pending") })}</Link>{task.actions.map(action => <p key={action.action_id}>{t(actionLabelKey(action.action_type))}: {t(`agent.states.${action.status}`, { defaultValue: t("agent.pending") })}{action.is_simulated ? <SimulatedBadge /> : null}</p>)}</li>)}</ul>{tasks.data?.next_cursor ? <p>{t("agent.recentTasksOnly")}</p> : null}
    </Card>
    <Card><h2 className="text-lg font-semibold">{t("agent.recentActions")}</h2><p>{t("agent.outcomeHint")}</p><ul className="mt-2 flex flex-col gap-2">{data.recent_actions.map(action => <li key={action.id}>{t(actionLabelKey(action.action_type))} | {t(`agent.states.${action.status}`, { defaultValue: t("agent.pending") })}</li>)}</ul>{!data.recent_actions.length ? <p>{t("agent.noActions")}</p> : null}</Card>
    {data.controller_mode === "legacy" ? <Link className="text-indigo-700 underline" to={`/w/${ws}/more/automation`}>{t("agent.legacySettings")}</Link> : null}
  </> : null}</>;
}
