import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { useDirtyForm } from "@/components/DirtyForms";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Notice } from "@/components/Feedback";
import { SelectField } from "@/components/FormFields";
import { CheckIcon, InfoIcon, PencilIcon, StoreIcon, UsersIcon } from "@/components/icons";
import { TextField } from "@/components/TextField";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useUpdateWorkspace } from "@/features/workspaces/hooks";
import { timezoneOptions } from "@/features/workspaces/wizardDefaults";
import { useMembers } from "./hooks";
import { DetailRow, LinkRow, PanelTitle, SettingsPanel, SettingsSection, TEXT_ACTION } from "./SettingsParts";
import { currencyLabel, timezoneLabel, timezoneOffset } from "./workspaceLabels";

const NAME_MAX = 100; // workspaces.name (identity schemas `Name`)

export function WorkspaceSection() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const members = useMembers(workspace.id);
  const base = `/w/${workspace.id}/more/settings`;
  const memberCount = members.data?.length;

  return (
    <SettingsSection id="workspace" title={t("settings.nav.workspace")} description={t("settings.workspace.description")}>
      <WorkspaceDetails canEdit={role === "owner"} />

      <SettingsPanel aria-label={t("settings.workspace.adminTitle")}>
        <LinkRow
          to={`${base}/members`}
          icon={<UsersIcon />}
          label={t("settings.workspace.team")}
          description={role === "owner" ? t("settings.workspace.teamOwnerHint") : t("settings.workspace.teamHint")}
          meta={memberCount !== undefined ? t("settings.workspace.memberCount", { count: memberCount }) : undefined}
        />
        {role === "owner" || role === "manager" ? (
          <LinkRow
            to={`${base}/system-health`}
            icon={<InfoIcon />}
            label={t("settings.workspace.systemHealth")}
            description={t("settings.workspace.systemHealthHint")}
          />
        ) : null}
      </SettingsPanel>
    </SettingsSection>
  );
}

function WorkspaceDetails({ canEdit }: { canEdit: boolean }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const language = i18n.language;
  const replyLanguages = [workspace.default_locale, ...workspace.reply_languages.filter((l) => l !== workspace.default_locale)]
    .filter((l) => workspace.reply_languages.includes(l))
    .map((l) => t(`settings.languages.${l}`, { lng: l }));

  return (
    <SettingsPanel as="section" aria-labelledby="settings-workspace-details">
      <PanelTitle
        id="settings-workspace-details"
        icon={<StoreIcon />}
        title={t("settings.workspace.detailsTitle")}
        description={
          saved && !editing ? (
            <span role="status" className="inline-flex items-center gap-1 font-medium text-success">
              <CheckIcon aria-hidden="true" />
              {t("settings.workspace.saved")}
            </span>
          ) : canEdit ? (
            t("settings.workspace.detailsHint")
          ) : (
            t("settings.workspace.ownerOnly")
          )
        }
        action={
          canEdit && !editing ? (
            <button
              type="button"
              className={TEXT_ACTION}
              onClick={() => {
                setSaved(false);
                setEditing(true);
              }}
            >
              <PencilIcon aria-hidden="true" />
              {t("settings.workspace.edit")}
            </button>
          ) : undefined
        }
      />
      {editing ? (
        <WorkspaceEditForm
          onDone={(didSave) => {
            setEditing(false);
            setSaved(didSave);
          }}
        />
      ) : (
        <dl className="pb-1">
          <DetailRow term={t("settings.workspace.name")}>{workspace.name}</DetailRow>
          <DetailRow term={t("settings.workspace.businessType")}>{t(`wizard.categories.${workspace.business_category}`)}</DetailRow>
          <DetailRow term={t("settings.workspace.region")}>{t(`settings.workspace.markets.${workspace.market}`)}</DetailRow>
          <DetailRow term={t("settings.workspace.currency")}>{currencyLabel(workspace.currency, language)}</DetailRow>
          <DetailRow term={t("settings.workspace.timezone")} hint={t("settings.workspace.timezoneHint")}>
            {timezoneLabel(workspace.timezone, language)}
          </DetailRow>
          <DetailRow term={t("settings.workspace.replyLanguages")} hint={t("settings.workspace.replyLanguagesHint")}>
            {replyLanguages.join(", ")}
          </DetailRow>
          <DetailRow term={t("settings.workspace.created")}>
            {new Date(workspace.created_at).toLocaleDateString(language, { dateStyle: "long", timeZone: workspace.timezone })}
          </DetailRow>
        </dl>
      )}
    </SettingsPanel>
  );
}

/** Owner-only edit of the two details that are safe to change after setup: name and time zone. */
function WorkspaceEditForm({ onDone }: { onDone: (saved: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const update = useUpdateWorkspace(workspace.id);
  const [name, setName] = useState(workspace.name);
  const [timezone, setTimezone] = useState(workspace.timezone);
  const [nameError, setNameError] = useState<string | undefined>();
  const zones = useMemo(() => timezoneOptions(workspace.timezone), [workspace.timezone]);
  const zoneLabels = useMemo(() => {
    const now = new Date();
    return new Map(
      zones.map((zone) => {
        const offset = timezoneOffset(zone, i18n.language, now);
        return [zone, offset ? `${zone.replaceAll("_", " ")} (${offset})` : zone.replaceAll("_", " ")];
      }),
    );
  }, [zones, i18n.language]);
  const changes = {
    ...(name.trim() !== workspace.name ? { name: name.trim() } : {}),
    ...(timezone !== workspace.timezone ? { timezone } : {}),
  };
  const dirty = Object.keys(changes).length > 0;
  useDirtyForm(dirty && !update.isSuccess);

  const serverNameError = update.error?.fieldErrors.find((e) => e.field === "name");
  const serverZoneError = update.error?.fieldErrors.find((e) => e.field === "timezone");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setNameError(t("settings.workspace.nameRequired"));
    if (!dirty) return onDone(false);
    update.mutate(changes, { onSuccess: () => onDone(true) });
  };

  return (
    <form onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-4 border-t border-border/70 px-4 py-4 sm:px-5 sm:pb-5">
      <TextField
        label={t("settings.workspace.name")}
        value={name}
        maxLength={NAME_MAX}
        autoFocus
        error={nameError ?? (serverNameError ? t("settings.workspace.nameInvalid") : undefined)}
        onChange={(event) => {
          setName(event.target.value);
          setNameError(undefined);
        }}
      />
      <SelectField
        label={t("settings.workspace.timezone")}
        hint={t("settings.workspace.timezoneHint")}
        error={serverZoneError ? t("settings.workspace.timezoneInvalid") : undefined}
        value={timezone}
        onChange={(event) => setTimezone(event.target.value)}
      >
        {zones.map((zone) => (
          <option key={zone} value={zone}>
            {zoneLabels.get(zone)}
          </option>
        ))}
      </SelectField>
      {timezone !== workspace.timezone ? (
        <Notice tone="attention" title={t("settings.workspace.timezoneChangeTitle")}>
          {t("settings.workspace.timezoneChangeBody", { zone: timezoneLabel(timezone, i18n.language) })}
        </Notice>
      ) : null}
      {update.isError && !serverNameError && !serverZoneError ? <ErrorMessage error={update.error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" pending={update.isPending} disabled={!dirty}>
          {t("settings.saveChanges")}
        </Button>
        <Button variant="ghost" disabled={update.isPending} onClick={() => onDone(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}
