import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Button } from "@/components/Button";
import { MagnifierIcon, MenuIcon } from "@/components/icons";
import { useMeta } from "@/features/auth/hooks";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { WorkspaceSwitcher } from "@/features/workspaces/WorkspaceSwitcher";
import { DestinationLauncher } from "./DestinationLauncher";
import { DESTINATION_GROUPS, NAV_ITEMS, allowedDestination, selectedDestination, shellContext, workspaceTarget } from "./navigation";
import { SimulationBanner } from "./SimulationBanner";

/** The five phone tabs retain their URLs; desktop exposes daily work directly. */
export function AppShell() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const meta = useMeta();
  const location = useLocation();
  const [expanded, setExpanded] = useState(false);
  const [launcher, setLauncher] = useState<"pointer" | "shortcut" | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const prefix = `/w/${workspace.id}`;
  const path = location.pathname === prefix ? "" : location.pathname.slice(prefix.length + 1);
  const selected = selectedDestination(path);
  const context = shellContext(path);
  const productName = meta.data?.product_name ?? t("app.name");
  const groups = DESTINATION_GROUPS.map(group => ({ ...group, items: group.items.filter(item => allowedDestination(item, role, Boolean(meta.data?.demo_tools_enabled))) }));
  const parent = groups.flatMap(group => group.items).find(item => item.path === context.parent);
  const account = new URLSearchParams(location.search).get("account");
  const parentSearch = parent?.path.startsWith("more/agent") && account ? `?${new URLSearchParams({ account })}` : "";

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        // A feature modal owns its keyboard while open.
        if (document.querySelector('[role="dialog"]')) return;
        event.preventDefault(); setLauncher("shortcut");
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);

  return <div className="flex min-h-dvh flex-col bg-canvas text-primary md:flex-row">
    <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-30 focus:rounded-control focus:bg-surface focus:p-3 focus:outline-2 focus:outline-focus">{t("app.skipToContent")}</a>
    <aside data-testid="desktop-sidebar" className={`sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto bg-navigation px-3 py-6 text-navigation-text md:flex min-[1200px]:w-60 ${expanded ? "w-60" : "w-24"}`}>
      <span title={productName} className="mb-6 min-w-0 break-words px-3 font-heading text-xl font-bold">
        <span className={expanded ? "" : "sr-only min-[1200px]:not-sr-only"}>{productName}</span>
        {!expanded ? <span aria-hidden="true" className="block text-center min-[1200px]:hidden">{t("shell.compactBrand")}</span> : null}
      </span>
      <button type="button" onClick={() => setExpanded(value => !value)} aria-expanded={expanded} aria-controls="desktop-destinations" className="mb-3 flex min-h-11 items-center justify-center gap-2 rounded-control text-navigation-text hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-focus-inverse min-[1200px]:hidden"><MenuIcon className="text-xl" /><span className={expanded ? "" : "sr-only"}>{t("shell.expandNavigation")}</span></button>
      <nav id="desktop-destinations" aria-label={t("nav.label")} className="flex flex-col gap-5">
        {groups.map(group => <div key={group.labelKey}>
          <p className={`mb-2 px-3 text-xs font-medium text-navigation-text ${expanded ? "" : "sr-only min-[1200px]:not-sr-only"}`}>{t(group.labelKey)}</p>
          <ul className="flex flex-col gap-1">{group.items.map(({ path: destination, labelKey, icon: Icon }) => <li key={destination}>
            <Link to={workspaceTarget(workspace.id, destination)} aria-current={selected === destination ? "page" : undefined} title={t(labelKey)} className={`flex min-h-11 items-center gap-3 rounded-control px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-inverse ${expanded ? "" : "justify-center min-[1200px]:justify-start"} ${selected === destination ? "bg-navigation-selected text-primary" : "text-navigation-text hover:bg-white/10"}`}><Icon className="shrink-0 text-xl" /><span className={expanded ? "" : "sr-only min-[1200px]:not-sr-only"}>{t(labelKey)}</span></Link>
          </li>)}</ul>
        </div>)}
      </nav>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex min-w-0 flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-3 md:px-6 min-[1200px]:px-8">
        <span className="w-full min-w-0 break-words font-heading text-base font-bold md:hidden">{productName}</span>
        <div className="ml-auto flex w-full min-w-0 max-w-full items-center justify-between gap-1 md:w-auto md:justify-start">
          <WorkspaceSwitcher />
          <Button ref={trigger} variant="ghost" onClick={() => setLauncher("pointer")} aria-label={t("shell.openLauncher")} aria-haspopup="dialog" className="min-w-11 px-2"><MagnifierIcon className="text-xl" /><span className="hidden min-[1200px]:inline">{t("shell.openLauncher")}</span><kbd className="hidden rounded border border-border px-1 text-xs text-secondary min-[1200px]:inline">{t("shell.shortcut")}</kbd></Button>
          <NotificationBell />
        </div>
      </header>
      <SimulationBanner offline={meta.data?.llm_mode === "fake"} />
      <main id="main" tabIndex={-1} data-content-width={context.width} className={`mx-auto w-full min-w-0 flex-1 px-4 py-5 pb-[calc(6rem+env(safe-area-inset-bottom))] outline-none md:px-6 md:pb-8 min-[1200px]:px-8 ${context.width === "reading" ? "max-w-3xl" : "max-w-[1440px]"}`}>
        <nav aria-label={t("shell.breadcrumb")} className="mb-5 text-metadata text-secondary">
          <ol className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <li className="min-w-0 max-w-full"><Link to={prefix} className="break-words underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-focus">{workspace.name}</Link></li>
            {parent ? <li><span aria-hidden="true" className="mr-2">/</span><Link to={`${workspaceTarget(workspace.id, parent.path)}${parentSearch}`} className="underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-focus">{t(parent.labelKey)}</Link></li> : null}
            <li className="min-w-0"><span aria-hidden="true" className="mr-2">/</span><span className="break-words" aria-current="page">{t(context.labelKey)}</span></li>
          </ol>
        </nav>
        <Outlet key={workspace.id} />
      </main>
    </div>
    <nav aria-label={t("nav.label")} className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden">
      {NAV_ITEMS.map(({ path: destination, labelKey, icon: Icon }) => {
        const active = destination === "more" ? path === "more" || path.startsWith("more/") : selected === destination;
        return <Link key={destination} to={workspaceTarget(workspace.id, destination)} aria-current={active ? "page" : undefined} className={`flex min-h-16 min-w-0 flex-col items-center justify-center gap-1 px-1 py-2 text-center text-xs leading-tight font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${active ? "bg-surface-subtle text-action" : "text-secondary"}`}><Icon className="text-2xl" /><span className="max-w-full break-words">{t(labelKey)}</span></Link>;
      })}
    </nav>
    {launcher ? <DestinationLauncher workspaceId={workspace.id} role={role} demoTools={Boolean(meta.data?.demo_tools_enabled)} onClose={() => setLauncher(null)} returnFocusRef={launcher === "pointer" ? trigger : undefined} /> : null}
  </div>;
}
