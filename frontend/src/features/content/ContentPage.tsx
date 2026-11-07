import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import type { ContentTab } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { PageHeader } from "@/components/Layout";
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
    <div className="flex min-w-0 flex-col gap-6">
      {/* Page Header & Action Controls */}
      <PageHeader title={t("content.title")} description={t("content.intro")} action={
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setStarting("ai")} className="gap-2 shadow-xs">
            <SparkIcon className="text-lg text-on-action" />
            <span>{t("content.actions.newDraft")}</span>
          </Button>
          <Button variant="secondary" onClick={() => setStarting("blank")} className="gap-2 shadow-xs">
            <PlusIcon className="text-lg" />
            <span>{t("content.actions.blankDraft")}</span>
          </Button>
        </div>
      } />

      {/* View Switcher: Library vs Agenda */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
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
            className={`inline-flex min-h-11 items-center gap-2 rounded-control px-3 text-body font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
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
            className={`inline-flex min-h-11 items-center gap-2 rounded-control px-3 text-body font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
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
            className="flex flex-wrap items-center gap-1 border-b border-border"
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
                  className={`min-h-11 border-b-2 px-4 py-2 text-body font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                    isSelected
                      ? "border-action text-action"
                      : "border-transparent text-secondary hover:text-primary hover:bg-surface-subtle"
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
            <Card className="overflow-hidden p-0">
              <ul className="flex flex-col divide-y divide-border" aria-label={t(`content.tabs.${tab}`)}>
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
