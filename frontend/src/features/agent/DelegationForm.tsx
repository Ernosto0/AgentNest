import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { newRequestId } from "@/features/commands/hooks";
import { ACTIONS, actionLabelKey, usePreviewDelegation, useApplyDelegation, type Schema } from "./hooks";
import { FIELD } from "./PersonalityForm";
export function DelegationForm({ ws, account, config, data, owner }: {
    ws: string;
    account: string;
    config: number;
    data: Schema<"DelegationOut"> | null;
    owner: boolean;
}) {
    const { t } = useTranslation();
    const [policy, setPolicy] = useState<Schema<"DelegationPolicy">>(data?.policy ?? { actions: Object.fromEntries(ACTIONS.map(a => [a, { mode: "off", sources: ["customer", "owner_task"], max_per_day: null }])) });
    const [proposal, setProposal] = useState<Schema<"DelegationChange"> | null>(null);
    const preview = usePreviewDelegation(ws, account), apply = useApplyDelegation(ws, account);
    const locked = preview.isPending || apply.isPending;
    function edit(action: string, change: Partial<Schema<"ActionRule">>) { setProposal(null); preview.reset(); apply.reset(); setPolicy({ ...policy, actions: { ...policy.actions, [action]: { ...policy.actions[action]!, ...change } } }); }
    return <Card className="flex flex-col gap-3"><h2 className="text-lg font-semibold">{t("agent.delegation")}</h2><p>{t("agent.delegationHint")}</p>
    {ACTIONS.map(action => <fieldset key={action} className="min-w-0 rounded-lg border border-slate-200 p-3" disabled={!owner || locked}><legend className="px-1 font-medium">{t(actionLabelKey(action))}</legend><div className="grid gap-2 sm:grid-cols-2"><label>{t("agent.mode")}<select className={FIELD} value={policy.actions[action]!.mode} onChange={e => edit(action, { mode: e.target.value as Schema<"ActionRule">["mode"] })}>{["automatic", "ask", "off"].map(m => <option key={m} value={m}>{t(`agent.modes.${m}`)}</option>)}</select></label><label>{t("agent.dailyLimit")}<input className={FIELD} type="number" min={1} max={10000} value={policy.actions[action]!.max_per_day ?? ""} onChange={e => edit(action, { max_per_day: e.target.value ? Number(e.target.value) : null })}/></label></div><div className="mt-2 flex flex-wrap gap-4">{(["customer", "owner_task"] as const).map(source => <label key={source} className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={policy.actions[action]!.sources.includes(source)} onChange={e => edit(action, { sources: e.target.checked ? [...policy.actions[action]!.sources, source] : policy.actions[action]!.sources.filter(s => s !== source) })}/>{t(`agent.sources.${source}`)}</label>)}</div></fieldset>)}
    {owner ? <Button disabled={locked} onClick={() => { const body = { policy, expected_config_version: config, expected_delegation_version: data?.version ?? null, client_request_id: newRequestId() }; setProposal(null); preview.mutate(body, { onSuccess: () => setProposal(body) }); }}>{t("agent.previewDelegation")}</Button> : <p>{t("agent.ownerOnly")}</p>}
    {preview.data && proposal ? <div role="status"><p>{t("agent.versionPreview", { version: preview.data.next_version })}</p><ul>{preview.data.changed_actions.map(a => <li key={a}>{t(actionLabelKey(a))}: {t(`agent.modes.${data?.policy.actions[a]?.mode ?? "off"}`)} {" -> "} {t(`agent.modes.${proposal.policy.actions[a]!.mode}`)}<p>{t("agent.dailyLimit")}: {data?.policy.actions[a]?.max_per_day ?? t("agent.noAdditionalLimit")} {" -> "} {proposal.policy.actions[a]!.max_per_day ?? t("agent.noAdditionalLimit")}</p><p>{(data?.policy.actions[a]?.sources ?? ["customer", "owner_task"]).map(source => t(`agent.sources.${source}`)).join(", ") || t("agent.noSources")} {" -> "} {proposal.policy.actions[a]!.sources.map(source => t(`agent.sources.${source}`)).join(", ") || t("agent.noSources")}</p></li>)}</ul><p>{t("agent.changeWarning")}</p><Button disabled={locked} onClick={() => apply.mutate(proposal, { onSuccess: () => { setProposal(null); preview.reset(); } })}>{t("agent.applyDelegation")}</Button></div> : null}
    {preview.error ? <ErrorMessage error={preview.error}/> : null}{apply.error ? <ErrorMessage error={apply.error}/> : null}{apply.isSuccess ? <p role="status">{t("agent.saved")}</p> : null}
  </Card>;
}
