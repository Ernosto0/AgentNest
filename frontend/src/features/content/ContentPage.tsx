import { useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import type { ContentTab, ContentType } from "@/api/types";
import { PageHeader } from "@/components/Layout";
import { CalendarIcon, ImageIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AgendaView } from "./AgendaView";
import { ContentComposer } from "./ContentComposer";
import { GenerateSheet, type NewContentMode } from "./GenerateSheet";
import { LIST_LIMIT, useAllContentTabs } from "./hooks";
import { LibraryView, type TabList } from "./LibraryView";
import { tabItems } from "./presentation";
import { CONTENT_TABS, isContentTab, tabOfStatusParam } from "./status";

type View = "library" | "agenda";
type Sheet = { mode: NewContentMode; type: ContentType; objective?: string };

const VIEWS: readonly View[] = ["library", "agenda"];
const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/**
 * Content (ui-spec R08): start a post or story, then see everything by what needs doing (the
 * library's status tabs) or by when it goes out (the agenda). The address keeps the view, tab,
 * week and layout, so links from Today and the daily report land on the right place.
 */
export function ContentPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();

  const view: View = params.get("view") === "agenda" ? "agenda" : "library";
  const setView = (next: View) => {
    const search = new URLSearchParams(params);
    if (next === "library") search.delete("view");
    else search.set("view", next);
    setParams(search, { replace: true });
  };

  const requested = params.get("tab");
  // `?status=on_hold` is the shortcut the daily report links to: it opens the tab that lists that status.
  const byStatus = tabOfStatusParam(params.get("status"));
  const tab: ContentTab = isContentTab(requested) ? requested : (byStatus ?? "drafts");
  const setTab = (next: ContentTab) => {
    const search = new URLSearchParams(params);
    search.set("tab", next);
    search.delete("status");
    setParams(search, { replace: true });
  };

  // Every tab's list feeds the status tiles and the agenda's empty state (one cache with the open tab).
  const queries = useAllContentTabs(workspace.id, CONTENT_TABS);
  const lists = Object.fromEntries(
    CONTENT_TABS.map((name, index) => {
      const query = queries[index];
      const list: TabList = {
        items: tabItems(query?.data, name),
        capped: (query?.data?.length ?? 0) >= LIST_LIMIT,
        isError: query?.isError ?? false,
      };
      return [name, list];
    }),
  ) as Record<ContentTab, TabList>;

  // One sheet for every way in: the composer, its blank-draft action and the empty states.
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const composerInput = useRef<HTMLInputElement>(null);
  const focusComposer = () => {
    const input = composerInput.current;
    if (!input) return;
    input.scrollIntoView?.({ block: "center", behavior: "smooth" });
    input.focus({ preventScroll: true });
  };

  return (
    <div className="flex min-w-0 flex-col gap-5 pb-4">
      <PageHeader
        title={t("content.title")}
        description={t("content.intro")}
        action={<ViewSwitch view={view} onChange={setView} />}
      />

      <ContentComposer inputRef={composerInput} onStart={(mode, type, objective) => setSheet({ mode, type, objective })} />

      {view === "agenda" ? (
        <AgendaView draftCount={lists.drafts.items?.length ?? 0} onWrite={focusComposer} />
      ) : (
        <LibraryView tab={tab} onTab={setTab} lists={lists} onWrite={focusComposer} />
      )}

      {sheet ? (
        <GenerateSheet
          initialMode={sheet.mode}
          initialType={sheet.type}
          initialObjective={sheet.objective}
          onClose={() => setSheet(null)}
        />
      ) : null}
    </div>
  );
}

/** Library or agenda: two tabs over the same content. Arrow keys move between them. */
function ViewSwitch({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const { t } = useTranslation();
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next: View =
      event.key === "Home" ? "library" : event.key === "End" ? "agenda" : view === "library" ? "agenda" : "library";
    onChange(next);
    document.getElementById(`content-view-${next}`)?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label={t("content.viewsLabel")}
      onKeyDown={onKeyDown}
      className="inline-flex rounded-xl border border-border bg-surface-subtle/80 p-1"
    >
      {VIEWS.map((name) => {
        const selected = view === name;
        const Icon = name === "library" ? ImageIcon : CalendarIcon;
        return (
          <button
            key={name}
            id={`content-view-${name}`}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(name)}
            className={`inline-flex min-h-11 items-center gap-2 rounded-lg px-3.5 md:min-h-10 text-body font-semibold transition-colors ${FOCUS} ${
              selected ? "bg-surface text-primary shadow-xs ring-1 ring-border" : "text-secondary hover:text-primary"
            }`}
          >
            <Icon aria-hidden="true" className={`text-base ${selected ? "text-action" : ""}`} />
            <span>{t(name === "library" ? "content.viewLibrary" : "content.viewAgenda")}</span>
          </button>
        );
      })}
    </div>
  );
}
