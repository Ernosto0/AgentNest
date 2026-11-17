import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { components } from "@/api/schema";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { MediaUpload } from "@/features/content/MediaUpload";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useBrand, useSaveBrand } from "./hooks";
import { SettingsPanel } from "./SettingsParts";

export function BrandSection() {
  const { workspace, role } = useCurrentWorkspace();
  const query = useBrand(workspace.id);
  const { t } = useTranslation();
  return <SettingsPanel aria-label={t("brand.title")}>
    <h3 className="type-section">{t("brand.title")}</h3>
    {query.error ? <ErrorMessage error={query.error} /> : null}
    {query.data ? <BrandForm key={workspace.id} brand={query.data} workspaceId={workspace.id} canEdit={role === "owner" || role === "manager"} /> : null}
  </SettingsPanel>;
}

function BrandForm({ brand, workspaceId, canEdit }: { brand: components["schemas"]["BrandOut"]; workspaceId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [primary, setPrimary] = useState(brand.primary_color);
  const [accent, setAccent] = useState(brand.accent_color);
  const [logo, setLogo] = useState(brand.logo_media_asset_id);
  const [invalid, setInvalid] = useState(false);
  const save = useSaveBrand(workspaceId);
  const busy = save.isPending;
  const colors = [
    { id: "primary", label: t("brand.primary"), value: primary, set: setPrimary },
    { id: "accent", label: t("brand.accent"), value: accent, set: setAccent },
  ];
  return <form className="mt-4 flex min-w-0 flex-col gap-4" onSubmit={event => {
    event.preventDefault();
    const valid = colors.every(color => /^#[0-9a-fA-F]{6}$/.test(color.value));
    setInvalid(!valid);
    if (valid && canEdit) save.mutate({ primary_color: primary.toLowerCase(), accent_color: accent.toLowerCase(), logo_media_asset_id: logo });
  }}>
    <fieldset disabled={!canEdit || busy} className="flex min-w-0 flex-col gap-4">
      {colors.map(color => <div key={color.id} className="flex min-w-0 flex-wrap items-center gap-3">
        <label htmlFor={`brand-${color.id}`} className="w-full text-sm font-medium">{color.label}</label>
        <input type="color" aria-label={t("brand.picker", { name: color.label })} value={/^#[0-9a-fA-F]{6}$/.test(color.value) ? color.value : "#000000"} onChange={event => { color.set(event.target.value); save.reset(); }} className="size-11" />
        <input id={`brand-${color.id}`} value={color.value} onChange={event => { color.set(event.target.value); save.reset(); }} maxLength={7} spellCheck={false} aria-invalid={invalid} className="min-h-11 min-w-0 flex-1 rounded-control border border-border bg-surface px-3" />
      </div>)}
    </fieldset>
    {invalid ? <p role="alert" className="text-danger">{t("brand.invalid")}</p> : null}
    <p className="text-sm font-medium">{t("brand.logo")}</p>
    <MediaUpload workspaceId={workspaceId} contentType="feed_image" mediaId={logo} onUploaded={asset => { setLogo(asset.id); save.reset(); }} disabled={!canEdit || busy} />
    {logo && canEdit ? <Button type="button" disabled={busy} onClick={() => { setLogo(null); save.reset(); }}>{t("brand.remove")}</Button> : null}
    {save.error ? <ErrorMessage error={save.error} /> : null}
    {save.isSuccess ? <Notice tone="success" title={t("brand.saved")} live="polite" /> : null}
    {canEdit ? <Button type="submit" disabled={busy}>{t("brand.save")}</Button> : <p className="text-sm text-secondary">{t("brand.readOnly")}</p>}
  </form>;
}
