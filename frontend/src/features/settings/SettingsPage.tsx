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
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-slate-500/10 via-emerald-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <h1 className="text-2xl sm:text-3xl font-heading font-extrabold tracking-tight text-primary">{t("settings.title")}</h1>
      </div>

      {/* Account Identity */}
      <div className="flex flex-col gap-4 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">{t("settings.account")}</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-surface-subtle/70 p-4 border border-border/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary">{t("settings.signedInAs")}</p>
            <p className="mt-1 text-sm font-bold text-primary break-words">
              {me.data?.user.display_name}
            </p>
            <p className="text-xs text-secondary break-all font-mono mt-0.5">{me.data?.user.email}</p>
          </div>
          <div className="rounded-xl bg-surface-subtle/70 p-4 border border-border/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary">{t("settings.role")}</p>
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
      <div className="flex flex-col gap-3 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">{t("settings.language")}</h2>
        </div>
        <p className="text-sm text-secondary leading-relaxed">{t("settings.languageHint")}</p>
        <div className="pt-1">
          <LanguageSwitch onChange={(language) => saveLocale.mutate(language)} />
        </div>
        {saveLocale.isError ? <ErrorMessage error={saveLocale.error} /> : null}
      </div>

      {/* Workspace Details (Read-only) */}
      <div className="flex flex-col gap-4 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
        <div className="border-b border-border/60 pb-3">
          <h2 className="text-base font-heading font-bold text-primary">
            {t("settings.workspaceDetails")}
          </h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-surface-subtle/70 p-4 border border-border/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary">{t("settings.workspaceName")}</p>
            <p className="mt-1 text-sm font-bold text-primary">{workspace.name}</p>
          </div>
          <div className="rounded-xl bg-surface-subtle/70 p-4 border border-border/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary">{t("settings.workspaceMarket")}</p>
            <p className="mt-1 text-sm font-bold text-primary">
              {workspace.market} · {workspace.currency}
            </p>
          </div>
          <div className="rounded-xl bg-surface-subtle/70 p-4 border border-border/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary">{t("settings.workspaceTimezone")}</p>
            <p className="mt-1 text-sm font-bold text-primary">{workspace.timezone}</p>
          </div>
        </div>
      </div>

      {/* Management Navigation Links */}
      <div className="flex flex-col gap-2 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
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
