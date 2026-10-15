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
  if (!isCategory(params.category)) return <NotFoundPage />;
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
    <div className="flex flex-col gap-5">
      <div>
        <Link
          to={`/w/${workspace.id}/more/knowledge`}
          className="inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          {t("knowledge.back")}
        </Link>
        <h1 className="text-2xl font-semibold">{t(`knowledge.category.${category}`)}</h1>
      </div>

      {template.error ?? facts.error ? <ErrorMessage error={template.error ?? facts.error} /> : null}
      {transition.error ? <ErrorMessage error={transition.error} /> : null}
      {!loaded && !(template.error ?? facts.error) ? <p>{t("common.loading")}</p> : null}

      {loaded?.entries.map((entry) => {
        if (entry.kind === "fixed") {
          if (entry.fact) return card(entry.fact);
          return (
            <Card key={entry.item.identifier} className="flex flex-col gap-2" data-testid={`missing-${entry.item.key}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="min-w-0 text-base font-semibold break-words">
                  {pickLabel(entry.item.label, i18n.language)}
                </h3>
                <FactStatusChip state="missing" />
              </div>
              <p className="text-sm text-slate-600">{pickLabel(entry.item.description, i18n.language)}</p>
              {entry.item.required_for ? (
                <p className="text-sm text-orange-900">
                  {t(`knowledge.required.${entry.item.required_for}`)}
                </p>
              ) : null}
              <div>
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
            <section key={entry.item.identifier} className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-medium">{pickLabel(entry.item.label, i18n.language)}</h2>
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
                <p className="text-sm text-slate-600">
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
          <section key="other" className="flex flex-col gap-3">
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

      {loaded && loaded.archived.length > 0 ? (
        <details className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
          <summary className="min-h-11 cursor-pointer py-2 font-medium">
            {t("knowledge.archived", { count: loaded.archived.length })}
          </summary>
          <div className="mt-3 flex flex-col gap-3">{loaded.archived.map(card)}</div>
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
