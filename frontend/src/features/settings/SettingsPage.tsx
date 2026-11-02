import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ChevronRightIcon } from "@/components/icons";
import { useLogout, useMe, useSaveLocale } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountSecurity } from "./AccountSecurity";
import { WorkspaceDangerZone } from "./WorkspaceDangerZone";

const LINK_ROW =
  "flex min-h-11 items-center justify-between rounded-control px-3 py-2 text-sm font-medium text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-focus transition-colors";

export function SettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const { workspace, role } = useCurrentWorkspace();
  const saveLocale = useSaveLocale();
  const logout = useLogout();

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => navigate("/login"),
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("settings.title")}</h1>
      </div>

      {/* Account Identity */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-base font-heading font-semibold text-primary">{t("settings.account")}</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-secondary">{t("settings.signedInAs")}</p>
            <p className="mt-0.5 text-sm font-medium text-primary break-words">
              {me.data?.user.display_name}
            </p>
            <p className="text-xs text-secondary break-all">{me.data?.user.email}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-secondary">{t("settings.role")}</p>
            <p className="mt-0.5 text-sm font-medium text-primary">
              {role ? t(`workspaces.role.${role}`) : "—"}
            </p>
          </div>
        </div>
        <div>
          <Button
            variant="ghost"
            disabled={logout.isPending}
            onClick={handleLogout}
            className="text-danger hover:bg-danger/10"
          >
            {logout.isPending ? t("auth.signingOut") : t("settings.signOut")}
          </Button>
        </div>
      </div>

      {/* Language Preference */}
      <div className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-base font-heading font-semibold text-primary">{t("settings.language")}</h2>
        <p className="text-sm text-secondary">{t("settings.languageHint")}</p>
        <div>
          <LanguageSwitch onChange={(language) => saveLocale.mutate(language)} />
        </div>
        {saveLocale.isError ? <ErrorMessage error={saveLocale.error} /> : null}
      </div>

      {/* Workspace Details (Read-only) */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-base font-heading font-semibold text-primary">
          {t("settings.workspaceDetails")}
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs font-medium text-secondary">{t("settings.workspaceName")}</p>
            <p className="mt-0.5 text-sm font-medium text-primary">{workspace.name}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-secondary">{t("settings.workspaceMarket")}</p>
            <p className="mt-0.5 text-sm font-medium text-primary">
              {workspace.market} · {workspace.currency}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-secondary">{t("settings.workspaceTimezone")}</p>
            <p className="mt-0.5 text-sm font-medium text-primary">{workspace.timezone}</p>
          </div>
        </div>
      </div>

      {/* Management Navigation Links */}
      <div className="flex flex-col gap-2 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-base font-heading font-semibold text-primary">
          {t("settings.workspaceSection")}
        </h2>
        <div className="flex flex-col divide-y divide-border">
          <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK_ROW}>
            <span>{t("settings.openConnections")}</span>
            <ChevronRightIcon className="text-xl text-secondary" />
          </Link>
          <Link to={`/w/${workspace.id}/more/settings/members`} className={LINK_ROW}>
            <span>{t("settings.openMembers")}</span>
            <ChevronRightIcon className="text-xl text-secondary" />
          </Link>
          {role === "owner" || role === "manager" ? (
            <Link to={`/w/${workspace.id}/more/settings/system-health`} className={LINK_ROW}>
              <span>{t("settings.openSystemHealth")}</span>
              <ChevronRightIcon className="text-xl text-secondary" />
            </Link>
          ) : null}
        </div>
      </div>

      {/* Security & Sessions */}
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-heading font-semibold text-primary">
            {t("settings.security")}
          </h2>
          <p className="mt-0.5 text-xs text-secondary leading-relaxed">{t("settings.securityDesc")}</p>
        </div>
        <AccountSecurity />
      </div>

      {/* Privacy Surface */}
      <div className="flex flex-col gap-2 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-sm font-heading font-semibold text-primary">
          {t("settings.privacy")}
        </h2>
        <p className="text-xs text-secondary leading-relaxed">{t("settings.privacyDesc")}</p>
      </div>

      {/* Danger Zone: Workspace Deletion (Owner only) */}
      {role === "owner" ? <WorkspaceDangerZone workspaceId={workspace.id} /> : null}
    </div>
  );
}
