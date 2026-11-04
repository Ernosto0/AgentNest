import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import type { ContentTab } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon, InboxIcon, PlusIcon, SparkIcon, SpinnerIcon } from "@/components/icons";
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
      {/* Page Header & Action Controls */}
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern sm:flex-row sm:items-center sm:justify-between flex flex-col gap-5">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-emerald-500/10 via-teal-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <div className="flex flex-col gap-1 relative z-10">
          <h1 className="type-page text-primary font-heading font-extrabold text-2xl sm:text-3xl tracking-tight">{t("content.title")}</h1>
          <p className="text-body text-secondary max-w-xl">{t("content.intro")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 relative z-10 shrink-0">
          <Button onClick={() => setStarting("ai")} className="gap-2 shadow-xs">
            <SparkIcon className="text-lg text-on-action" />
            <span>{t("content.actions.newDraft")}</span>
          </Button>
          <Button variant="secondary" onClick={() => setStarting("blank")} className="gap-2 shadow-xs">
            <PlusIcon className="text-lg" />
            <span>{t("content.actions.blankDraft")}</span>
          </Button>
        </div>
      </div>

      {/* View Switcher: Library vs Agenda */}
      <div className="flex items-center justify-between">
        <div
          role="tablist"
          aria-label={t("content.viewsLabel")}
          className="inline-flex rounded-xl bg-surface-subtle/80 p-1 border border-border/80 shadow-2xs"
        >
          <button
            type="button"
            role="tab"
            aria-selected={view === "library"}
            onClick={() => setView("library")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              view === "library"
                ? "bg-surface text-primary shadow-xs font-bold"
                : "text-secondary hover:text-primary hover:bg-surface/50"
            }`}
          >
            <InboxIcon className="text-sm" />
            <span>{t("content.viewLibrary")}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "agenda"}
            onClick={() => setView("agenda")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              view === "agenda"
                ? "bg-surface text-primary shadow-xs font-bold"
                : "text-secondary hover:text-primary hover:bg-surface/50"
            }`}
          >
            <CalendarIcon className="text-sm" />
            <span>{t("content.viewAgenda")}</span>
          </button>
        </div>
      </div>

      {view === "agenda" ? (
        <AgendaView />
      ) : (
        <>
          {/* Content Status Tabs */}
          <div
            role="tablist"
            aria-label={t("content.tabsLabel")}
            className="flex flex-wrap items-center gap-1.5 p-1 rounded-xl bg-surface-subtle/80 border border-border/80 shadow-2xs"
          >
            {CONTENT_TABS.map((name) => {
              const isSelected = tab === name;
              return (
                <button
                  key={name}
                  role="tab"
                  type="button"
                  aria-selected={isSelected}
                  onClick={() => setParams({ tab: name }, { replace: true })}
                  className={`min-h-9 rounded-lg px-4 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                    isSelected
                      ? "bg-surface text-primary shadow-xs font-bold ring-1 ring-border/50"
                      : "text-secondary hover:text-primary hover:bg-surface/50"
                  }`}
                >
                  {t(`content.tabs.${name}`)}
                </button>
              );
            })}
          </div>

          {items.isError ? <ErrorMessage error={items.error} /> : null}
          {items.isPending ? (
            <div className="flex items-center gap-2 py-4 text-sm text-secondary">
              <SpinnerIcon className="motion-safe:animate-spin text-base text-action" />
              <p>{t("common.loading")}</p>
            </div>
          ) : null}
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
