import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRightIcon } from "@/components/icons";
import { useLogout, useMeta } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const ROW =
  "flex min-h-14 w-full items-center justify-between gap-3 rounded-xl bg-white px-4 text-left text-base font-medium text-slate-900 ring-1 ring-slate-200 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600";

export function MorePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { workspace, role } = useCurrentWorkspace();
  const logout = useLogout();
  const meta = useMeta();

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold">{t("more.title")}</h1>
      <ul className="flex flex-col gap-3">
        <li>
          <Link to={`/w/${workspace.id}/more/reports`} className={ROW}>
            {t("more.reports")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <Link to={`/w/${workspace.id}/more/notifications`} className={ROW}>
            {t("more.notifications")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        {role === "owner" || role === "manager" ? (
          <li>
            <Link to={`/w/${workspace.id}/more/activity`} className={ROW}>
              {t("more.activity")}
              <ChevronRightIcon className="text-xl text-slate-400" />
            </Link>
          </li>
        ) : null}
        <li>
          <Link to={`/w/${workspace.id}/more/knowledge`} className={ROW}>
            {t("more.knowledge")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <Link to={`/w/${workspace.id}/more/knowledge/answers`} className={ROW}>
            {t("more.answers")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <Link to={`/w/${workspace.id}/more/automation`} className={ROW}>
            {t("more.automation")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        {meta.data?.demo_tools_enabled ? (
          <li>
            <Link to={`/w/${workspace.id}/more/dev`} className={ROW}>
              {t("more.devPanel")}
              <ChevronRightIcon className="text-xl text-slate-400" />
            </Link>
          </li>
        ) : null}
        <li>
          <Link to={`/w/${workspace.id}/more/settings`} className={ROW}>
            {t("more.settings")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <Link to="/" className={ROW}>
            {t("more.switchWorkspace")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <Link to="/workspaces/new" className={ROW}>
            {t("more.newWorkspace")}
            <ChevronRightIcon className="text-xl text-slate-400" />
          </Link>
        </li>
        <li>
          <button
            type="button"
            className={ROW}
            disabled={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            {logout.isPending ? t("auth.signingOut") : t("more.signOut")}
          </button>
        </li>
      </ul>
    </div>
  );
}
