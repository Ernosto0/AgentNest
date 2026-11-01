import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import type { ContentTab } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { PlusIcon, SparkIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AgendaView } from "./AgendaView";
import { ContentCard } from "./ContentCard";
import { GenerateSheet, type NewContentMode } from "./GenerateSheet";
import { useContentItems } from "./hooks";
import { CONTENT_TABS, isContentTab, tabOf, tabOfStatusParam } from "./status";

/** Content by what needs doing: drafts, what is scheduled, what is out, and what went wrong. */
export function ContentPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();

  const viewParam = params.get("view");
  const view: "library" | "agenda" = viewParam === "agenda" ? "agenda" : "library";

  const setView = (nextView: "library" | "agenda") => {
    const next = new URLSearchParams(params);
    if (nextView === "library") {
      next.delete("view");
    } else {
      next.set("view", "agenda");
    }
    setParams(next, { replace: true });
  };

  const requested = params.get("tab");
  // `?status=on_hold` is the shortcut the daily report links to: it opens the tab that lists that status.
  const byStatus = tabOfStatusParam(params.get("status"));
  const tab: ContentTab = isContentTab(requested) ? requested : (byStatus ?? "drafts");
  const items = useContentItems(workspace.id, tab);
  // The server already filters by tab; a defensive filter keeps a cancelled or foreign-tab item out.
  const visible = items.data?.filter((item) => tabOf(item.status) === tab);
  // Two ways in: ask the assistant for a draft, or start with a blank one and write it yourself.
  const [starting, setStarting] = useState<NewContentMode | null>(null);

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{t("content.title")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t("content.intro")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Button onClick={() => setStarting("ai")} className="gap-2">
            <SparkIcon className="text-lg" />
            <span>{t("content.actions.newDraft")}</span>
          </Button>
          <Button variant="secondary" onClick={() => setStarting("blank")} className="gap-2">
            <PlusIcon className="text-lg" />
            <span>{t("content.actions.blankDraft")}</span>
          </Button>
        </div>
      </div>

      {/* View Switcher: Library vs Agenda */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div role="tablist" aria-label={t("content.viewsLabel")} className="inline-flex rounded-lg bg-slate-100 p-1">
          <button
            type="button"
            role="tab"
            aria-selected={view === "library"}
            onClick={() => setView("library")}
            className={`rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              view === "library" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("content.viewLibrary")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "agenda"}
            onClick={() => setView("agenda")}
            className={`rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              view === "agenda" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {t("content.viewAgenda")}
          </button>
        </div>
      </div>

      {view === "agenda" ? (
        <AgendaView />
      ) : (
        <>
          <div role="tablist" aria-label={t("content.tabsLabel")} className="flex flex-wrap gap-1.5">
            {CONTENT_TABS.map((name) => {
              const isSelected = tab === name;
              return (
                <button
                  key={name}
                  role="tab"
                  type="button"
                  aria-selected={isSelected}
                  onClick={() => setParams({ tab: name }, { replace: true })}
                  className={`min-h-10 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                    isSelected
                      ? "bg-indigo-700 text-white shadow-xs"
                      : "bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
                  }`}
                >
                  {t(`content.tabs.${name}`)}
                </button>
              );
            })}
          </div>

          {items.isError ? <ErrorMessage error={items.error} /> : null}
          {items.isPending ? <p className="text-sm text-slate-500">{t("common.loading")}</p> : null}
          {visible && visible.length === 0 ? (
            <EmptyState title={t(`content.empty.${tab}`)} description={t("content.empty.hint")} />
          ) : null}
          {visible && visible.length > 0 ? (
            <Card className="p-0 border-0 bg-transparent shadow-none ring-0">
              <ul className="flex flex-col gap-3" aria-label={t(`content.tabs.${tab}`)}>
                {visible.map((item) => (
                  <li key={item.id}>
                    <ContentCard item={item} />
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </>
      )}

      {starting ? <GenerateSheet initialMode={starting} onClose={() => setStarting(null)} /> : null}
    </div>
  );
}
