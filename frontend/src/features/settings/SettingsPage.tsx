import { PageHeader } from "@/components/Layout";
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
  "flex min-h-12 items-center justify-between rounded-xl px-4 py-3 text-sm font-semibold text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus transition-all duration-150";

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
    <div className="flex flex-col gap-8">
      <PageHeader title={t("settings.title")} />

      <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
      {/* Account Identity */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 sm:p-6">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">{t("settings.account")}</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="min-w-0 py-1">
            <p className="text-xs font-semibold tracking-wide text-secondary">{t("settings.signedInAs")}</p>
            <p className="mt-1 text-sm font-bold text-primary break-words">
              {me.data?.user.display_name}
            </p>
            <p className="text-body text-secondary break-all mt-0.5">{me.data?.user.email}</p>
          </div>
          <div className="min-w-0 py-1">
            <p className="text-xs font-semibold tracking-wide text-secondary">{t("settings.role")}</p>
            <p className="mt-1 text-sm font-bold text-primary">
              {role ? t(`workspaces.role.${role}`) : "—"}
            </p>
          </div>
        </div>
        <div className="pt-1">
          <Button
            variant="ghost"
            disabled={logout.isPending}
            onClick={handleLogout}
            className="text-danger hover:bg-danger-subtle font-semibold"
          >
            {logout.isPending ? t("auth.signingOut") : t("settings.signOut")}
          </Button>
        </div>
      </div>

      {/* Language Preference */}
      <div className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 sm:p-6">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">{t("settings.language")}</h2>
        </div>
        <p className="text-sm text-secondary leading-relaxed">{t("settings.languageHint")}</p>
        <div className="pt-1">
          <LanguageSwitch onChange={(language) => saveLocale.mutate(language)} />
        </div>
        {saveLocale.isError ? <ErrorMessage error={saveLocale.error} /> : null}
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

        </div>
        <div className="flex min-w-0 flex-col gap-6">
      {/* Workspace Details (Read-only) */}
      <div className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-5 sm:p-6">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">
            {t("settings.workspaceDetails")}
          </h2>
        </div>
        <div className="grid gap-4">
          <div className="min-w-0 py-1">
            <p className="text-xs font-semibold tracking-wide text-secondary">{t("settings.workspaceName")}</p>
            <p className="mt-1 text-sm font-bold text-primary">{workspace.name}</p>
          </div>
          <div className="min-w-0 py-1">
            <p className="text-xs font-semibold tracking-wide text-secondary">{t("settings.workspaceMarket")}</p>
            <p className="mt-1 text-sm font-bold text-primary">
              {workspace.market} · {workspace.currency}
            </p>
          </div>
          <div className="min-w-0 py-1">
            <p className="text-xs font-semibold tracking-wide text-secondary">{t("settings.workspaceTimezone")}</p>
            <p className="mt-1 text-sm font-bold text-primary">{workspace.timezone}</p>
          </div>
        </div>
      </div>

      {/* Management Navigation Links */}
      <div className="flex flex-col gap-2 rounded-panel border border-border bg-surface p-5 sm:p-6">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">
            {t("settings.workspaceSection")}
          </h2>
        </div>
        <div className="flex flex-col divide-y divide-border/60">
          <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK_ROW}>
            <span>{t("settings.openConnections")}</span>
            <ChevronRightIcon className="text-xl text-secondary/50" />
          </Link>
          <Link to={`/w/${workspace.id}/more/settings/members`} className={LINK_ROW}>
            <span>{t("settings.openMembers")}</span>
            <ChevronRightIcon className="text-xl text-secondary/50" />
          </Link>
          {role === "owner" || role === "manager" ? (
            <Link to={`/w/${workspace.id}/more/settings/system-health`} className={LINK_ROW}>
              <span>{t("settings.openSystemHealth")}</span>
              <ChevronRightIcon className="text-xl text-secondary/50" />
            </Link>
          ) : null}
        </div>
      </div>

      {/* Privacy Surface */}
      <div className="flex flex-col gap-2 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="text-sm font-heading font-semibold text-primary">
          {t("settings.privacy")}
        </h2>
        <p className="text-xs text-secondary leading-relaxed">{t("settings.privacyDesc")}</p>
      </div>

        </div>
      </div>
      {/* Danger Zone: Workspace Deletion (Owner only) */}
      {role === "owner" ? <WorkspaceDangerZone workspaceId={workspace.id} /> : null}
    </div>
  );
}
