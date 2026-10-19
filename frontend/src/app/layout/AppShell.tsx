import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";
import { useMeta } from "@/features/auth/hooks";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { WorkspaceSwitcher } from "@/features/workspaces/WorkspaceSwitcher";
import { NAV_ITEMS } from "./navigation";
import { SimulationBanner } from "./SimulationBanner";

function useNavTarget() {
  const { workspace } = useCurrentWorkspace();
  return (path: string) => (path ? `/w/${workspace.id}/${path}` : `/w/${workspace.id}`);
}

/**
 * Mobile: top bar plus a bottom tab bar. Desktop (>= 768 px): the same items in a sidebar.
 * The simulation banner sits above everything on demo workspaces.
 */
export function AppShell() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const target = useNavTarget();
  const productName = meta.data?.product_name ?? t("app.name");

  return (
    <div className="flex min-h-dvh flex-col bg-slate-50 text-slate-900 md:flex-row">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-30 focus:bg-white focus:p-3"
      >
        {t("app.skipToContent")}
      </a>

      <aside className="hidden w-60 shrink-0 flex-col gap-6 border-r border-slate-200 bg-white p-4 md:flex">
        <span className="text-lg font-semibold text-indigo-800">{productName}</span>
        <nav aria-label={t("nav.label")} className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ path, labelKey, icon: Icon }) => (
            <NavLink
              key={labelKey}
              to={target(path)}
              end={path === ""}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-3 rounded-lg px-3 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                  isActive ? "bg-indigo-50 text-indigo-900" : "text-slate-700 hover:bg-slate-100"
                }`
              }
            >
              <Icon className="text-xl" />
              {t(labelKey)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {workspace.is_demo ? <SimulationBanner /> : null}
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
          <span className="truncate font-semibold text-indigo-800 md:hidden">{productName}</span>
          <div className="ml-auto flex min-w-0 items-center gap-1">
            <WorkspaceSwitcher />
            <NotificationBell />
          </div>
        </header>
        {meta.data?.llm_mode === "fake" ? (
          <p
            role="status"
            data-testid="ai-mode"
            className="border-b border-slate-200 bg-slate-100 px-4 py-1 text-center text-xs text-slate-700"
          >
            {t("aiMode.offline")}
          </p>
        ) : null}
        <main id="main" className="mx-auto w-full min-w-0 max-w-3xl flex-1 px-4 py-5 pb-28 md:px-8 md:pb-8">
          <Outlet />
        </main>
      </div>

      <nav
        aria-label={t("nav.label")}
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {NAV_ITEMS.map(({ path, labelKey, icon: Icon }) => (
          <NavLink
            key={labelKey}
            to={target(path)}
            end={path === ""}
            className={({ isActive }) =>
              `flex min-h-14 min-w-0 flex-col items-center justify-center gap-0.5 px-0.5 py-1.5 text-center text-[11px] leading-tight font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-600 ${
                isActive ? "text-indigo-800" : "text-slate-600"
              }`
            }
          >
            <Icon className="text-2xl" />
            <span className="max-w-full break-words">{t(labelKey)}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
