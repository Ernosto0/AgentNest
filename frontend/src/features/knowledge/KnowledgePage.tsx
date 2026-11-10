import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ErrorMessage } from "@/components/ErrorMessage";
import { BookIcon, ChevronRightIcon } from "@/components/icons";
import { PageHeader } from "@/components/Layout";
import { FOCUS } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AttentionPanel } from "./AttentionPanel";
import { CategoryBrowser } from "./CategoryBrowser";
import { knowledgeBase, useKnowledgeBase } from "./useKnowledgeBase";
import { KnowledgeStats } from "./KnowledgeStats";
import { attentionItems, overview } from "./model";
import { PasteExtractSheet } from "./PasteExtractSheet";
import { SetupPanel } from "./SetupPanel";
import { TeachPanel } from "./TeachPanel";

/**
 * The knowledge hub: what the assistant knows (counts), what needs the owner (blockers,
 * suggestions, facts on hold), every category to browse or search, and, beside them, the
 * paste-and-extract entry and the setup checklist.
 */
export function KnowledgePage() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canVerify = role !== "staff";
  const kb = useKnowledgeBase(workspace.id);
  const [pasting, setPasting] = useState(false);

  // Suggestions and readiness only add to the picture; a failure there must not hide the facts.
  const settled = kb.loaded && !kb.candidates.isPending && !kb.readiness.isPending;
  const stats = kb.summaries && settled ? overview(kb.summaries, kb.candidates.data, kb.readiness.data) : null;
  const attention = kb.loaded && settled ? attentionItems(kb.loaded.facts, kb.candidates.data, kb.readiness.data) : null;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader title={t("knowledge.title")} description={t("knowledge.intro")} />

      {kb.error ? <ErrorMessage error={kb.error} /> : null}

      {kb.error ? null : <KnowledgeStats data={stats} />}

      <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_21rem] xl:grid-rows-[auto_1fr]">
        {kb.error ? null : (
          <div className="min-w-0 xl:col-start-1 xl:row-start-1">
            <AttentionPanel items={attention} canVerify={canVerify} />
          </div>
        )}

        <aside aria-label={t("knowledge.asideLabel")} className="grid min-w-0 items-start gap-4 md:grid-cols-2 xl:col-start-2 xl:row-span-2 xl:row-start-1 xl:grid-cols-1">
          <TeachPanel onPaste={() => setPasting(true)} />
          <SetupPanel readiness={kb.readiness.data} error={kb.readiness.error} />
          <Link
            to={`${knowledgeBase(workspace.id)}/answers`}
            className={`group flex min-w-0 items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-3 md:col-span-2 xl:col-span-1 transition-colors hover:border-action/35 hover:bg-surface-subtle/50 ${FOCUS}`}
          >
            <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-subtle text-base text-action">
              <BookIcon />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-body leading-5 font-semibold text-primary group-hover:text-action">{t("more.answers")}</span>
              <span className="block text-xs text-secondary">{t("knowledge.answersHint")}</span>
            </span>
            <ChevronRightIcon aria-hidden="true" className="shrink-0 text-lg text-secondary/50 group-hover:text-primary" />
          </Link>
        </aside>

        {kb.error ? null : (
          <CategoryBrowser
            className="xl:col-start-1 xl:row-start-2"
            summaries={kb.summaries}
            facts={kb.loaded?.facts ?? []}
            template={kb.loaded?.template ?? []}
            needed={kb.needed}
          />
        )}
      </div>

      {pasting ? <PasteExtractSheet onClose={() => setPasting(false)} /> : null}
    </div>
  );
}
