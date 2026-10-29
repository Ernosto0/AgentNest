import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useSavePersonality, useAgentPersonality, type Schema } from "./hooks";
export const FIELD = "min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white p-2";
const choices = { tone: ["warm", "neutral", "direct"], formality: ["casual", "professional"], length: ["short", "medium"], emoji: ["none", "sparse"], dm_style: ["conversational", "concise"], comment_style: ["conversational", "concise"] } as const;
export function PersonalityForm({ ws, account, data, editable }: {
    ws: string;
    account: string;
    data: Schema<"PersonalityOut">;
    editable: boolean;
}) {
    const { t, i18n } = useTranslation();
    const [draft, setDraft] = useState(data.personality);
    const [version, setVersion] = useState(data.version);
    const [goals, setGoals] = useState(data.goals);
    const [preview, setPreview] = useState(false);
    const save = useSavePersonality(ws, account);
    const current = useAgentPersonality(ws, account);
    return <Card className="flex flex-col gap-3"><h2 className="text-lg font-semibold">{t("agent.personality")}</h2>
    <label>{t("agent.goals")}<textarea className={FIELD} maxLength={500} value={goals} disabled={!editable || save.isPending} onChange={e => {save.reset();setGoals(e.target.value);}}/></label>
    <p className="text-sm text-slate-600">{t("agent.goalsHint")}</p>
    <div className="grid gap-3 sm:grid-cols-2">{Object.entries(choices).map(([key, values]) => <label key={key}>{t(`agent.voice.${key}`)}<select className={FIELD} disabled={!editable || save.isPending} value={draft[key as keyof typeof choices]} onChange={e => { save.reset(); setPreview(false); setDraft({ ...draft, [key]: e.target.value }); }}>{values.map(v => <option key={v} value={v}>{t(`agent.voice.${v}`)}</option>)}</select></label>)}</div>
    {(["tr", "en"] as const).map(lang => <label key={lang}>{t(`agent.examples_${lang}`)}<textarea className={FIELD} disabled={!editable || save.isPending} value={draft.examples?.[lang]?.join("\n") ?? ""} maxLength={321} onChange={e => {save.reset();setDraft({ ...draft, examples: { ...draft.examples, [lang]: e.target.value.split("\n").slice(0, 2).map(s => s.slice(0, 160)) } });}}/></label>)}
    {editable ? <Button disabled={save.isPending} onClick={() => save.mutate({ expected_version: version, personality: draft, goals }, {onSuccess: saved => setVersion(saved.version)})}>{t("agent.savePersonality")}</Button> : <p>{t("agent.managerOnly")}</p>}
    {save.error ? <><ErrorMessage error={save.error}/><p>{t("agent.reloadWarning")}</p><Button variant="secondary" disabled={current.isFetching} onClick={() => {void current.refetch().then(result => {if(result.data){setDraft(result.data.personality);setGoals(result.data.goals);setVersion(result.data.version);save.reset();}});}}>{t("agent.reloadCurrent")}</Button></> : null}{save.isSuccess ? <p role="status">{t("agent.saved")}</p> : null}
    <Button variant="secondary" onClick={() => setPreview(v => !v)}>{t("agent.previewVoice")}</Button>
    {preview ? <aside className="rounded-lg bg-slate-50 p-3" aria-label={t("agent.previewVoice")}><p>{t("agent.previewDisclosure")}</p><p className="mt-2">{t("agent.sampleCustomer")}</p><p>{draft.examples?.[i18n.language === "en" ? "en" : "tr"]?.[0] || t(`agent.sample_${draft.tone}`)}{draft.emoji === "sparse" ? " " + String.fromCodePoint(0x1f642) : ""}</p></aside> : null}
  </Card>;
}
