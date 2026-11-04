import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { MORE_GROUPS, allowedDestination, workspaceTarget } from "@/app/layout/navigation";
import { Button } from "@/components/Button";
import { ListRow, PageHeader } from "@/components/Layout";
import { ChevronRightIcon } from "@/components/icons";
import { useLogout, useMeta } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const ROW = "flex min-h-11 min-w-0 items-center gap-3 rounded-control px-2 py-2 text-form font-medium text-primary hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-focus";

export function MorePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { workspace, role } = useCurrentWorkspace();
  const logout = useLogout();
  const meta = useMeta();
  return <div className="flex flex-col gap-6 max-w-4xl">
    <PageHeader title={t("more.title")} description={t("shell.moreHint")} />
    <div className="grid min-w-0 gap-6 min-[1000px]:grid-cols-2">
      {MORE_GROUPS.map(group => <section key={group.labelKey} aria-label={t(group.labelKey)} className="min-w-0 rounded-panel border border-border bg-surface p-5 shadow-xs">
        <h2 className="type-section px-2 pb-2 border-b border-border mb-2">{t(group.labelKey)}</h2>
        <ul>{group.items.filter(item => allowedDestination(item, role, Boolean(meta.data?.demo_tools_enabled))).map(({ path, labelKey, icon: Icon }) => <ListRow key={path} className="py-1">
          <Link to={workspaceTarget(workspace.id, path)} className={ROW}><Icon className="shrink-0 text-xl text-secondary" /><span className="min-w-0 flex-1 break-words">{t(labelKey)}</span><ChevronRightIcon className="shrink-0 text-xl text-secondary" /></Link>
        </ListRow>)}</ul>
      </section>)}
    </div>
    <section aria-label={t("shell.account")} className="rounded-panel border border-border bg-surface p-5 shadow-xs">
      <h2 className="type-section px-2 pb-2 border-b border-border mb-2">{t("shell.account")}</h2>
      <ul>
        <ListRow className="py-1"><Link to="/" className={ROW}>{t("more.switchWorkspace")}<ChevronRightIcon className="ml-auto shrink-0 text-xl text-secondary" /></Link></ListRow>
        <ListRow className="py-1"><Link to="/workspaces/new" className={ROW}>{t("more.newWorkspace")}<ChevronRightIcon className="ml-auto shrink-0 text-xl text-secondary" /></Link></ListRow>
      </ul>
      <Button variant="ghost" pending={logout.isPending} onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })} className="mt-3 text-danger hover:bg-danger-subtle">{logout.isPending ? t("auth.signingOut") : t("more.signOut")}</Button>
    </section>
  </div>;
}
