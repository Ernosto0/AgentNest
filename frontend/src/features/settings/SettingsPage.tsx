import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { useMe, useSaveLocale } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const LINK =
  "min-h-11 py-2 font-semibold text-indigo-700 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600";

export function SettingsPage() {
  const { t } = useTranslation();
  const me = useMe();
  const { workspace, role } = useCurrentWorkspace();
  const saveLocale = useSaveLocale();

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">{t("settings.language")}</h2>
        <p className="text-sm text-slate-600">{t("settings.languageHint")}</p>
        <LanguageSwitch onChange={(language) => saveLocale.mutate(language)} />
        {saveLocale.isError ? <ErrorMessage error={saveLocale.error} /> : null}
      </Card>

      <Card className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">{t("settings.workspaceSection")}</h2>
        <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK}>
          {t("settings.openConnections")}
        </Link>
        {role === "owner" || role === "manager" ? (
          <Link to={`/w/${workspace.id}/more/settings/system-health`} className={LINK}>
            {t("settings.openSystemHealth")}
          </Link>
        ) : null}
      </Card>

      <Card className="flex flex-col gap-1">
        <h2 className="text-lg font-medium">{t("settings.account")}</h2>
        <p className="text-sm text-slate-600">{t("settings.signedInAs")}</p>
        <p className="font-medium break-words">{me.data?.user.display_name}</p>
        <p className="text-sm break-all text-slate-600">{me.data?.user.email}</p>
      </Card>
    </div>
  );
}
