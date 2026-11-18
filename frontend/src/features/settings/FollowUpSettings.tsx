import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { FollowUpSettingsBody, FollowUpSettingsData } from "@/api/types";
import { Button } from "@/components/Button";
import { useDirtyForm } from "@/components/DirtyForms";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { ChoiceField, SelectField, TextAreaField } from "@/components/FormFields";
import { ClockIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useFollowUpSettings, useSaveFollowUpSettings } from "./hooks";
import { PanelTitle, SettingsPanel } from "./SettingsParts";

export function FollowUpSettings() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const query = useFollowUpSettings(workspace.id);
  return <SettingsPanel as="section" aria-labelledby="follow-up-title">
    <PanelTitle id="follow-up-title" icon={<ClockIcon />} title={t("settings.followUp.title")} description={t("settings.followUp.description")} />
    {query.error ? <ErrorMessage error={query.error} /> : null}
    {query.data ? <FollowUpForm key={workspace.id} data={query.data} workspaceId={workspace.id} canEdit={role === "owner"} /> : null}
  </SettingsPanel>;
}

function FollowUpForm({ data, workspaceId, canEdit }: { data: FollowUpSettingsData; workspaceId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [form, setForm] = useState<FollowUpSettingsBody>({ enabled: data.enabled, hours: data.hours, text: data.text });
  const [baseline, setBaseline] = useState(form);
  const save = useSaveFollowUpSettings(workspaceId);
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  useDirtyForm(canEdit && dirty);
  const change = (value: FollowUpSettingsBody) => { setForm(value); save.reset(); };
  return <form className="flex min-w-0 flex-col gap-4 border-t border-border px-4 py-4 sm:px-5" onSubmit={event => {
    event.preventDefault();
    if (canEdit) save.mutate(form, { onSuccess: () => setBaseline(form) });
  }}>
    <fieldset disabled={!canEdit || save.isPending} className="flex min-w-0 flex-col gap-4">
      <ChoiceField label={t("settings.followUp.enabled")} checked={form.enabled} onChange={event => change({ ...form, enabled: event.target.checked })} />
      <SelectField label={t("settings.followUp.hours")} value={form.hours} onChange={event => change({ ...form, hours: Number(event.target.value) })}>
        {Array.from({ length: 20 }, (_, i) => i + 1).map(hours => <option key={hours} value={hours}>{hours}</option>)}
      </SelectField>
      {(["tr", "en"] as const).map(language => {
        const error = save.error?.fieldErrors.find(item => item.field === `text.${language}`);
        return <TextAreaField key={language} label={t(`settings.followUp.text.${language}`)} hint={t("settings.followUp.templateHint")} value={form.text[language]} placeholder={data.default_text[language]} maxLength={400} error={error ? t(`settings.followUp.errors.${error.code}`, { defaultValue: t("settings.followUp.errors.invalid") }) : undefined} onChange={event => change({ ...form, text: { ...form.text, [language]: event.target.value } })} />;
      })}
    </fieldset>
    {save.error ? <ErrorMessage error={save.error} /> : null}
    {save.isSuccess ? <Notice tone="success" title={t("settings.followUp.saved")} live="polite" /> : null}
    {canEdit ? <Button type="submit" pending={save.isPending} disabled={!dirty}>{t("settings.saveChanges")}</Button> : <p className="text-sm text-secondary">{t("settings.followUp.ownerOnly")}</p>}
  </form>;
}
