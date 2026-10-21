import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import type { ContentTab } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ContentCard } from "./ContentCard";
import { GenerateSheet, type NewContentMode } from "./GenerateSheet";
import { useContentItems } from "./hooks";
import { CONTENT_TABS, isContentTab, tabOf, tabOfStatusParam } from "./status";

/** Content by what needs doing: drafts, what is scheduled, what is out, and what went wrong. */
export function ContentPage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();
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
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("content.title")}</h1>
        <p className="mt-1 text-slate-600">{t("content.intro")}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setStarting("ai")}>{t("content.actions.newDraft")}</Button>
        <Button variant="secondary" onClick={() => setStarting("blank")}>
          {t("content.actions.blankDraft")}
        </Button>
      </div>

      <div role="tablist" aria-label={t("content.tabsLabel")} className="flex flex-wrap gap-2">
        {CONTENT_TABS.map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setParams({ tab: name }, { replace: true })}
            className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              tab === name ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
            }`}
          >
            {t(`content.tabs.${name}`)}
          </button>
        ))}
      </div>

      {items.isError ? <ErrorMessage error={items.error} /> : null}
      {items.isPending ? <p>{t("common.loading")}</p> : null}
      {visible && visible.length === 0 ? (
        <EmptyState title={t(`content.empty.${tab}`)} description={t("content.empty.hint")} />
      ) : null}
      {visible && visible.length > 0 ? (
        <Card className="p-0">
          <ul className="flex flex-col gap-3 p-3" aria-label={t(`content.tabs.${tab}`)}>
            {visible.map((item) => (
              <li key={item.id}>
                <ContentCard item={item} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {starting ? <GenerateSheet initialMode={starting} onClose={() => setStarting(null)} /> : null}
    </div>
  );
}
