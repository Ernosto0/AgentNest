import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { useDirtyForm } from "@/components/DirtyForms";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CheckIcon, LogOutIcon } from "@/components/icons";
import { TextField } from "@/components/TextField";
import { Segmented } from "@/features/agent/AgentParts";
import { useLogout, useMe, useSaveDisplayName, useSaveLocale } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { SUPPORTED_LANGUAGES, isLanguage, setLanguage, type Language } from "@/i18n";
import { SettingRow, SettingsPanel, SettingsSection, TEXT_ACTION } from "./SettingsParts";

const NAME_MAX = 100; // users.display_name (identity schemas `Name`)

/** Up to two initials, upper-cased with the UI locale so Turkish "i" becomes "İ". */
function initials(name: string, locale: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0]!, parts[parts.length - 1]!] : parts.slice(0, 1);
  return letters.map((part) => Array.from(part)[0] ?? "").join("").toLocaleUpperCase(locale) || "?";
}

export function AccountSection() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const { workspace, role } = useCurrentWorkspace();
  const logout = useLogout();
  const user = me.data?.user;

  return (
    <SettingsSection id="account" title={t("settings.nav.account")} description={t("settings.account.description")}>
      <SettingsPanel>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-5 sm:py-5">
          <div className="flex min-w-0 flex-1 basis-60 items-center gap-3.5">
            <span
              aria-hidden="true"
              className="flex size-12 shrink-0 items-center justify-center rounded-full bg-assistant font-heading text-base font-bold text-action"
            >
              {user ? initials(user.display_name, i18n.language) : ""}
            </span>
            <div className="min-w-0">
              <p className="font-heading text-base leading-snug font-semibold text-primary [overflow-wrap:anywhere]">
                {user?.display_name ?? "—"}
              </p>
              <p className="text-metadata text-secondary [overflow-wrap:anywhere]">{user?.email}</p>
            </div>
          </div>
          <Button
            variant="secondary"
            pending={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            className="sm:min-h-10"
          >
            {logout.isPending ? null : <LogOutIcon aria-hidden="true" />}
            {logout.isPending ? t("auth.signingOut") : t("settings.account.signOut")}
          </Button>
        </div>

        {user ? <DisplayNameRow current={user.display_name} /> : null}

        <SettingRow label={t("settings.account.role")} description={t("settings.account.roleHint", { workspace: workspace.name })}>
          <span className="inline-flex items-center rounded-full bg-surface-subtle px-2.5 py-0.5 text-metadata font-semibold text-primary ring-1 ring-border ring-inset">
            {t(`workspaces.role.${role}`)}
          </span>
        </SettingRow>

        <LanguageRow />
      </SettingsPanel>
    </SettingsSection>
  );
}

function DisplayNameRow({ current }: { current: string }) {
  const { t } = useTranslation();
  const save = useSaveDisplayName();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(current);
  const [error, setError] = useState<string | undefined>();
  const [saved, setSaved] = useState(false);
  useDirtyForm(editing && draft.trim() !== current);

  const start = () => {
    setDraft(current);
    setError(undefined);
    setSaved(false);
    save.reset();
    setEditing(true);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const name = draft.trim();
    if (!name) return setError(t("settings.account.nameRequired"));
    if (name === current) return setEditing(false);
    save.mutate(name, {
      onSuccess: () => {
        setEditing(false);
        setSaved(true);
      },
    });
  };

  if (!editing) {
    return (
      <SettingRow
        label={t("settings.account.displayName")}
        description={
          saved ? (
            <span role="status" className="inline-flex items-center gap-1 font-medium text-success">
              <CheckIcon aria-hidden="true" />
              {t("settings.account.nameSaved")}
            </span>
          ) : (
            t("settings.account.displayNameHint")
          )
        }
      >
        <span className="min-w-0 text-body text-primary [overflow-wrap:anywhere]">{current}</span>
        <button type="button" onClick={start} className={TEXT_ACTION} aria-label={t("settings.account.editName")}>
          {t("settings.edit")}
        </button>
      </SettingRow>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-3 border-t border-border/70 bg-surface-subtle/40 px-4 py-4 sm:px-5">
      <TextField
        label={t("settings.account.displayName")}
        hint={t("settings.account.displayNameHint")}
        error={error}
        value={draft}
        maxLength={NAME_MAX}
        autoComplete="name"
        autoFocus
        onChange={(event) => {
          setDraft(event.target.value);
          setError(undefined);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setEditing(false);
        }}
      />
      {save.isError ? <ErrorMessage error={save.error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" pending={save.isPending}>
          {t("settings.save")}
        </Button>
        <Button variant="ghost" disabled={save.isPending} onClick={() => setEditing(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

/** Interface language for this user only; saved to the account so other devices follow. */
function LanguageRow() {
  const { t, i18n } = useTranslation();
  const saveLocale = useSaveLocale();
  const current: Language = isLanguage(i18n.language) ? i18n.language : "tr";

  const choose = (language: Language) => {
    if (language === current) return;
    void setLanguage(language).then(() => saveLocale.mutate(language));
  };

  return (
    <SettingRow label={t("settings.account.language")} labelId="settings-language-label" description={t("settings.account.languageHint")} align="start">
      <div className="flex min-w-0 flex-col gap-1.5 sm:items-end">
        <Segmented
          label={t("settings.account.language")}
          hideLabel
          name="ui-language"
          value={current}
          options={SUPPORTED_LANGUAGES.map((language) => ({
            value: language,
            label: t(`settings.languages.${language}`, { lng: language }),
            lang: language,
          }))}
          onChange={choose}
        />
        <p aria-live="polite" className="min-h-5 text-metadata text-secondary">
          {saveLocale.isPending ? (
            t("common.saving")
          ) : saveLocale.isSuccess ? (
            <span className="inline-flex items-center gap-1 font-medium text-success">
              <CheckIcon aria-hidden="true" />
              {t("settings.account.languageSaved")}
            </span>
          ) : null}
        </p>
        {saveLocale.isError ? (
          <div className="flex flex-col gap-2 sm:max-w-sm">
            <ErrorMessage error={saveLocale.error} />
            <Button variant="secondary" onClick={() => saveLocale.mutate(current)} className="self-start sm:self-end">
              {t("common.retry")}
            </Button>
          </div>
        ) : null}
      </div>
    </SettingRow>
  );
}
