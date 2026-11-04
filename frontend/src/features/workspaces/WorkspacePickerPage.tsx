import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { PublicShell } from "@/app/layout/PublicShell";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronRightIcon, HomeIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useLogout, useMe, useSaveLocale } from "@/features/auth/hooks";

const LINK = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-action px-5 py-2.5 font-semibold text-on-action hover:bg-action-hover shadow-xs transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

export function WorkspacePickerPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  const logout = useLogout();
  const saveLocale = useSaveLocale();
  const memberships = me.data?.memberships ?? [];
  return <PublicShell title={t("workspaces.pickerTitle")} description={t("workspaces.pickerHint")}
    onLanguageChange={(language) => saveLocale.mutate(language)}
    action={<Button variant="ghost" pending={logout.isPending} onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}>{logout.isPending ? t("auth.signingOut") : t("auth.signOut")}</Button>}>
    {saveLocale.isError ? <div className="grid gap-3"><ErrorMessage error={saveLocale.error} /><Button variant="secondary" pending={saveLocale.isPending} onClick={() => { if (saveLocale.variables) saveLocale.mutate(saveLocale.variables); }}>{t("common.retry")}</Button></div> : null}
    <p className="text-body break-all text-secondary">{me.data?.user.email}</p>
    {memberships.length === 0 ? <EmptyState title={t("workspaces.none")} description={t("entry.noMembershipHint")} icon={<HomeIcon />} /> :
      <ul className="divide-y divide-border/60 rounded-2xl border border-border/80 bg-surface px-6 shadow-card-modern">
        {memberships.map(member => <li key={member.workspace_id}>
          <Link to={`/w/${member.workspace_id}`} className="flex min-h-20 min-w-0 items-center gap-4 py-5 hover:translate-x-0.5 transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-800 border border-emerald-500/20 shadow-2xs"><HomeIcon className="text-xl" /></span>
            <div className="min-w-0 flex-1"><p className="text-base font-heading font-bold break-words text-primary">{member.workspace_name}</p><p className="mt-1 flex flex-wrap items-center gap-2 text-body text-secondary"><span>{t(`workspaces.role.${member.role}`)}</span>{member.is_demo ? <><span>{t("workspaces.demoTag")}</span><SimulatedBadge /></> : null}</p></div>
            <ChevronRightIcon className="shrink-0 text-xl text-secondary/50" />
          </Link>
        </li>)}
      </ul>}
    <Link to="/workspaces/new" className={LINK}>{t("workspaces.create")}<ChevronRightIcon className="shrink-0" /></Link>
  </PublicShell>;
}
