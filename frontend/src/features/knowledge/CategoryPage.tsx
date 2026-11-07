import { PageHeader } from "@/components/Layout";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import type { Fact, FactCategory } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { NotFoundPage } from "@/app/NotFoundPage";
import { FactCard } from "./FactCard";
import { FactEditorSheet, type EditorTarget } from "./FactEditorSheet";
import { FactStatusChip } from "./FactStatusChip";
import { HistorySheet } from "./HistorySheet";
import { useFactTransition, useFacts, useTemplate } from "./hooks";
import { isCategory, pickLabel } from "./labels";
import { categoryEntries } from "./summary";

/** The facts of one category, the missing template items, and the editor sheets. */
export function CategoryPage() {
  const params = useParams();
  if (!isCategory(params.category)) return <NotFoundPage embedded />;
  return <CategoryScreen category={params.category} />;
}

function CategoryScreen({ category }: { category: FactCategory }) {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canVerify = role !== "staff";
  const template = useTemplate(workspace.id);
  const facts = useFacts(workspace.id);
  const transition = useFactTransition(workspace.id);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [history, setHistory] = useState<Fact | null>(null);

  const loaded = template.data && facts.data ? categoryEntries(category, template.data, facts.data) : null;
  const itemFor = (fact: Fact) => template.data?.find((i) => i.key === fact.key || (i.pattern && fact.key.startsWith(i.pattern.replace(/\*$/, "")))) ?? null;
  const busyId = transition.isPending ? transition.variables?.factId : undefined;

  const card = (fact: Fact) => (
    <FactCard
      key={fact.id}
      fact={fact}
      timezone={workspace.timezone}
      canVerify={canVerify}
      busy={busyId === fact.id}
      onEdit={() => setEditor({ mode: "edit", fact, item: itemFor(fact) })}
      onHistory={() => setHistory(fact)}
      onVerify={() =>
        transition.mutate({ factId: fact.id, action: "verify", expectedVersion: fact.current_version })
      }
      onRestore={() =>
        transition.mutate({ factId: fact.id, action: "restore", expectedVersion: fact.current_version })
      }
    />
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to={`/w/${workspace.id}/more/knowledge`}
          className="inline-flex min-h-11 items-center font-medium text-action hover:text-action-hover underline focus-visible:outline-2 focus-visible:outline-focus"
        >
          ← {t("knowledge.back")}
        </Link>
        <PageHeader title={t(`knowledge.category.${category}`)} />
      </div>

      {template.error ?? facts.error ? <ErrorMessage error={template.error ?? facts.error} /> : null}
      {transition.error ? <ErrorMessage error={transition.error} /> : null}
      {!loaded && !(template.error ?? facts.error) ? (
        <p role="status" className="text-sm text-secondary">{t("common.loading")}</p>
      ) : null}

      <div className="grid min-w-0 items-start gap-4 xl:grid-cols-2">
      {loaded?.entries.map((entry) => {
        if (entry.kind === "fixed") {
          if (entry.fact) return card(entry.fact);
          return (
            <Card key={entry.item.identifier} className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs" data-testid={`missing-${entry.item.key}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="min-w-0 text-base font-semibold text-primary break-words">
                  {pickLabel(entry.item.label, i18n.language)}
                </h3>
                <FactStatusChip state="missing" />
              </div>
              <p className="text-sm text-secondary">{pickLabel(entry.item.description, i18n.language)}</p>
              {entry.item.required_for ? (
                <p className="inline-flex items-center gap-1.5 text-xs text-attention font-medium bg-attention-subtle px-2.5 py-1 rounded-control border border-border w-fit">
                  {t(`knowledge.required.${entry.item.required_for}`)}
                </p>
              ) : null}
              <div className="pt-1">
                <Button
                  variant="secondary"
                  onClick={() => setEditor({ mode: "create", category, item: entry.item })}
                >
                  {canVerify ? t("knowledge.actions.add") : t("knowledge.actions.suggest")}
                </Button>
              </div>
            </Card>
          );
        }
        if (entry.kind === "pattern") {
          return (
            <section key={entry.item.identifier} className="flex min-w-0 flex-col gap-3 xl:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
                <h2 className="text-lg font-heading font-semibold text-primary">{pickLabel(entry.item.label, i18n.language)}</h2>
                {canVerify ? (
                  <Button
                    variant="secondary"
                    onClick={() => setEditor({ mode: "create", category, item: entry.item })}
                  >
                    {t("knowledge.actions.add")}
                  </Button>
                ) : null}
              </div>
              {entry.facts.length === 0 ? (
                <p className="text-sm text-secondary">
                  {pickLabel(entry.item.description, i18n.language)}
                  {entry.item.required_for ? ` ${t(`knowledge.required.${entry.item.required_for}`)}` : ""}
                </p>
              ) : (
                entry.facts.map(card)
              )}
            </section>
          );
        }
        return (
          <section key="other" className="flex min-w-0 flex-col gap-3 xl:col-span-2">
            {entry.facts.map(card)}
            {category === "custom" && canVerify ? (
              <div>
                <Button
                  variant="secondary"
                  onClick={() => setEditor({ mode: "create", category: "custom", item: null })}
                >
                  {t("knowledge.actions.addCustom")}
                </Button>
              </div>
            ) : null}
          </section>
        );
      })}

      </div>

      {loaded && loaded.archived.length > 0 ? (
        <details className="rounded-panel border border-border bg-surface p-4 shadow-xs group">
          <summary className="min-h-11 cursor-pointer py-1 font-medium text-primary select-none group-hover:text-action transition-colors">
            {t("knowledge.archived", { count: loaded.archived.length })}
          </summary>
          <div className="mt-3 flex flex-col gap-3 border-t border-border pt-3">{loaded.archived.map(card)}</div>
        </details>
      ) : null}

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
        <HistorySheet
          workspaceId={workspace.id}
          fact={history}
          timezone={workspace.timezone}
          onClose={() => setHistory(null)}
        />
      ) : null}
    </div>
  );
}
