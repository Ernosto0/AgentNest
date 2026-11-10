import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams } from "react-router-dom";
import type { Fact, FactCategory, TemplateItem } from "@/api/types";
import { NotFoundPage } from "@/app/NotFoundPage";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, ChevronLeftIcon, PlusIcon } from "@/components/icons";
import { FOCUS, SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { CategoryCounts } from "./CategoryCounts";
import { CategoryNav } from "./CategoryNav";
import { FactEditorSheet, type EditorTarget } from "./FactEditorSheet";
import { FactRow, NotAddedRow } from "./FactRow";
import { HistorySheet } from "./HistorySheet";
import { useFactTransition } from "./hooks";
import { CategoryGlyph } from "./CategoryGlyph";
import { knowledgeBase, useKnowledgeBase } from "./useKnowledgeBase";
import { isCategory, pickLabel } from "./labels";
import { categoryView, itemForFact, needsReview } from "./model";

/** One category: its facts, what is not added yet, archived facts, and the editor sheets. */
export function CategoryPage() {
  const params = useParams();
  if (!isCategory(params.category)) return <NotFoundPage embedded />;
  return <CategoryScreen key={params.category} category={params.category} />;
}

const SECTION_TITLE = "font-heading text-base leading-snug font-semibold tracking-tight text-primary";

function CategoryScreen({ category }: { category: FactCategory }) {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canVerify = role !== "staff";
  const base = knowledgeBase(workspace.id);
  const kb = useKnowledgeBase(workspace.id);
  const transition = useFactTransition(workspace.id);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [history, setHistory] = useState<Fact | null>(null);
  const { hash } = useLocation();

  const view = kb.loaded ? categoryView(category, kb.loaded.template, kb.loaded.facts, kb.needed) : null;
  const summary = kb.summaries?.find((s) => s.category === category) ?? null;
  const busyId = transition.isPending ? transition.variables?.factId : undefined;
  const neededKeys = new Set(summary?.needed.flatMap((r) => r.missing_keys) ?? []);
  const isNeededFact = (fact: Fact) =>
    needsReview(fact) && [...neededKeys].some((id) => (id.endsWith(".*") ? fact.key.startsWith(id.slice(0, -1)) : id === fact.key));

  // Deep links (#fact-… / #item-…) from the overview and search: scroll there and mark it briefly.
  const ready = view !== null;
  useEffect(() => {
    if (!ready || !hash) return;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return;
    target.scrollIntoView?.({ block: "center" });
    target.setAttribute("data-highlight", "true");
    const timer = window.setTimeout(() => target.removeAttribute("data-highlight"), 2400);
    return () => window.clearTimeout(timer);
  }, [ready, hash]);

  const addLabel = (item: TemplateItem) => {
    const text = t("knowledge.page.addKind", { kind: pickLabel(item.label, i18n.language).toLocaleLowerCase(i18n.language) });
    return text.charAt(0).toLocaleUpperCase(i18n.language) + text.slice(1);
  };
  const addActions = canVerify
    ? [
        ...(view?.patterns ?? []).map((item) => ({ key: item.identifier, label: addLabel(item), target: { mode: "create", category, item } as EditorTarget })),
        ...(category === "custom" ? [{ key: "custom", label: t("knowledge.actions.addCustom"), target: { mode: "create", category: "custom", item: null } as EditorTarget }] : []),
      ]
    : [];

  const row = (fact: Fact) => (
    <FactRow
      key={fact.id}
      fact={fact}
      timezone={workspace.timezone}
      canVerify={canVerify}
      busy={busyId === fact.id}
      needed={isNeededFact(fact)}
      onEdit={() => setEditor({ mode: "edit", fact, item: kb.loaded ? itemForFact(kb.loaded.template, fact) : null })}
      onHistory={() => setHistory(fact)}
      onVerify={() => transition.mutate({ factId: fact.id, action: "verify", expectedVersion: fact.current_version })}
      onRestore={() => transition.mutate({ factId: fact.id, action: "restore", expectedVersion: fact.current_version })}
    />
  );

  // Needed items that share a group (phone / WhatsApp / email): any one of them is enough.
  const groupCounts = new Map<string, number>();
  for (const n of view?.notAdded ?? []) {
    if (n.needed && n.item.required_group) groupCounts.set(n.item.required_group, (groupCounts.get(n.item.required_group) ?? 0) + 1);
  }
  const isOneOf = (item: TemplateItem) => item.required_group !== null && (groupCounts.get(item.required_group) ?? 0) > 1;
  const groupHint = [...groupCounts.values()].some((count) => count > 1) ? t("knowledge.page.anyOne") : null;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="flex min-w-0 flex-col gap-3">
        <Link
          to={base}
          className={`-ml-1 inline-flex min-h-11 items-center gap-1 self-start rounded-control px-1 text-metadata font-semibold text-action hover:text-action-hover ${FOCUS}`}
        >
          <ChevronLeftIcon aria-hidden="true" className="text-base" />
          {t("knowledge.back")}
        </Link>
        <header className="flex min-w-0 flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="flex min-w-0 flex-1 basis-64 items-center gap-3">
            <CategoryGlyph category={category} />
            <div className="min-w-0">
              <h1 className="type-page break-words text-primary">{t(`knowledge.category.${category}`)}</h1>
              {summary ? <CategoryCounts summary={summary} /> : null}
            </div>
          </div>
          {addActions.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {addActions.map((action) => (
                <Button key={action.key} onClick={() => setEditor(action.target)}>
                  <PlusIcon className="text-base" />
                  {action.label}
                </Button>
              ))}
            </div>
          ) : null}
        </header>
      </div>

      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[13.5rem_minmax(0,1fr)] lg:gap-8">
        <CategoryNav current={category} base={base} summaries={kb.summaries} />

        <div className="flex min-w-0 flex-col gap-6">
          {kb.error ? <ErrorMessage error={kb.error} /> : null}
          {transition.error ? <ErrorMessage error={transition.error} /> : null}
          {!view && !kb.error ? <SkeletonRows label={t("common.loading")} rows={4} /> : null}

          {summary && summary.needed.length > 0 ? (
            <div role="status" data-testid="category-needed" className="flex min-w-0 items-start gap-3 rounded-xl bg-attention-subtle px-4 py-3">
              <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0 text-lg text-attention" />
              <div className="min-w-0">
                <p className="text-body font-semibold text-primary">
                  {summary.needed.map((r) => t(`readiness.requirement.${r.code}`)).join(" · ")}
                </p>
                <p className="text-metadata text-secondary">
                  {t(`knowledge.attention.needed.${summary.needed.some((r) => r.required_for === "drafts") ? "drafts" : "ready"}`)}
                  {groupHint ? ` ${groupHint}` : ""}
                </p>
              </div>
            </div>
          ) : null}

          {view && (view.facts.length > 0 || view.notAdded.length === 0) ? (
            <section aria-labelledby="category-facts" className="flex min-w-0 flex-col gap-2.5">
              <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3">
                <h2 id="category-facts" className={SECTION_TITLE}>
                  {t("knowledge.page.facts")}
                  {view.facts.length > 0 ? <span className="ml-2 text-metadata font-medium text-secondary tabular-nums">{view.facts.length}</span> : null}
                </h2>
                <p className="text-xs text-secondary">{t("knowledge.page.factsHint")}</p>
              </div>
              {view.facts.length > 0 ? (
                <ul className="min-w-0 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
                  {view.facts.map(row)}
                </ul>
              ) : (
                <div data-testid="category-empty" className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-border bg-surface/60 px-5 py-6">
                  <div>
                    <p className="font-heading text-base font-semibold text-primary">{t("knowledge.page.empty")}</p>
                    <p className="mt-0.5 max-w-prose text-metadata text-secondary">
                      {view.patterns.length > 0
                        ? view.patterns.map((item) => pickLabel(item.description, i18n.language)).join(" ")
                        : t("knowledge.page.emptyHint")}
                    </p>
                  </div>
                  {addActions.map((action) => (
                    <Button key={action.key} variant="secondary" onClick={() => setEditor(action.target)}>
                      <PlusIcon className="text-base" />
                      {action.label}
                    </Button>
                  ))}
                </div>
              )}
            </section>
          ) : null}

          {view && view.notAdded.length > 0 ? (
            <section aria-labelledby="category-not-added" className="flex min-w-0 flex-col gap-2.5">
              <div className="min-w-0">
                <h2 id="category-not-added" className={SECTION_TITLE}>
                  {t("knowledge.page.notAdded")}
                  <span className="ml-2 text-metadata font-medium text-secondary tabular-nums">{view.notAdded.length}</span>
                </h2>
                <p className="text-xs text-secondary">{t("knowledge.page.notAddedHint")}</p>
              </div>
              <ul className="flex min-w-0 flex-col gap-2">
                {view.notAdded.map(({ item, needed }) => (
                  <NotAddedRow
                    key={item.identifier}
                    item={item}
                    needed={needed}
                    oneOf={needed && isOneOf(item)}
                    canVerify={canVerify}
                    onAdd={item.key !== null || canVerify ? () => setEditor({ mode: "create", category, item }) : undefined}
                  />
                ))}
              </ul>
            </section>
          ) : null}

          {view && view.archived.length > 0 ? (
            <details className="group rounded-2xl border border-border bg-surface">
              <summary className={`flex min-h-11 cursor-pointer items-center rounded-2xl px-4 py-2 text-metadata font-semibold text-secondary select-none hover:text-primary sm:px-5 ${FOCUS}`}>
                {t("knowledge.archived", { count: view.archived.length })}
              </summary>
              <ul className="divide-y divide-border border-t border-border">{view.archived.map(row)}</ul>
            </details>
          ) : null}
        </div>
      </div>

      {editor ? (
        <FactEditorSheet
          key={editor.mode === "edit" ? editor.fact.id : (editor.item?.identifier ?? "custom")}
          workspaceId={workspace.id}
          currency={workspace.currency}
          canVerify={canVerify}
          target={editor}
          onClose={() => setEditor(null)}
        />
      ) : null}
      {history ? (
        <HistorySheet workspaceId={workspace.id} fact={history} timezone={workspace.timezone} onClose={() => setHistory(null)} />
      ) : null}
    </div>
  );
}
