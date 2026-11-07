import { PageHeader } from "@/components/Layout";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronRightIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FactStatusChip } from "./FactStatusChip";
import { useCandidates, useFacts, useReadiness, useTemplate } from "./hooks";
import { PasteExtractSheet } from "./PasteExtractSheet";
import { ReadinessChecklist } from "./ReadinessChecklist";
import { summarize } from "./summary";

const ROW =
  "group flex min-h-20 w-full min-w-0 items-center justify-between gap-4 p-4 sm:px-5 text-left hover:bg-surface-subtle transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus";

/** Business knowledge overview: readiness, suggestions, and one row per category. */
export function KnowledgePage() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const base = `/w/${workspace.id}/more/knowledge`;
  const template = useTemplate(workspace.id);
  const facts = useFacts(workspace.id);
  const candidates = useCandidates(workspace.id);
  const readiness = useReadiness(workspace.id);
  const [pasting, setPasting] = useState(false);

  const loadError = template.error ?? facts.error;
  const summaries = template.data && facts.data ? summarize(template.data, facts.data) : [];
  const pending = candidates.data?.length ?? 0;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title={t("knowledge.title")} description={t("knowledge.intro")} action={<Button variant="secondary" onClick={() => setPasting(true)} data-testid="open-paste-extract">{t("extract.open")}</Button>} />

      {loadError ? <ErrorMessage error={loadError} /> : null}
      {template.isPending || facts.isPending ? (
        <p role="status" className="text-sm text-secondary">{t("common.loading")}</p>
      ) : null}

      <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 overflow-hidden rounded-panel border border-border bg-surface">
      <Link to={`${base}/suggestions`} className={ROW}>
        <span className="min-w-0">
          <span className="block font-heading font-bold text-primary text-base group-hover:text-action transition-colors">
            {t("knowledge.suggestions.link")}
          </span>
          <span className="block text-sm text-secondary font-medium mt-0.5">
            {pending > 0
              ? t("knowledge.suggestions.waiting", { count: pending })
              : t("knowledge.suggestions.none")}
          </span>
        </span>
        <div className="flex items-center gap-2">
          {pending > 0 ? (
            <span className="inline-flex items-center rounded-full bg-attention-subtle px-2.5 py-0.5 text-xs font-bold text-attention border border-border">
              {pending}
            </span>
          ) : null}
          <ChevronRightIcon className="shrink-0 text-xl text-secondary/50 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
        </div>
      </Link>

      <ul className="divide-y divide-border border-t border-border" aria-label={t("knowledge.categories")}>
        {summaries.map((summary) => (
          <li key={summary.category}>
            <Link to={`${base}/${summary.category}`} className={ROW} data-category={summary.category}>
              <span className="min-w-0 flex-1">
                <span className="block font-heading font-bold text-primary text-base group-hover:text-action transition-colors">
                  {t(`knowledge.category.${summary.category}`)}
                </span>
                <span className="mt-2.5 flex flex-wrap items-center gap-2.5">
                  {summary.verified > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary font-medium">
                      <FactStatusChip state="verified" />
                      <span className="font-bold text-primary text-xs">{summary.verified}</span>
                    </span>
                  ) : null}
                  {summary.attention > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary font-medium">
                      <FactStatusChip state="unverified" />
                      <span className="font-bold text-primary text-xs">{summary.attention}</span>
                    </span>
                  ) : null}
                  {summary.missing > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary font-medium">
                      <FactStatusChip state="missing" />
                      <span className="font-bold text-primary text-xs">{summary.missing}</span>
                    </span>
                  ) : null}
                </span>
              </span>
              <ChevronRightIcon className="shrink-0 text-xl text-secondary/50 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
            </Link>
          </li>
        ))}
      </ul>
      </div>
      <aside className="order-first min-w-0 xl:order-last">
      {readiness.data ? (
        <Card className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5">
          <div className="flex items-center justify-between border-b border-border/60 pb-3">
            <h2 className="text-base font-heading font-bold text-primary">{t("readiness.title")}</h2>
          </div>
          <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} />
        </Card>
      ) : null}

      {pasting ? <PasteExtractSheet onClose={() => setPasting(false)} /> : null}

      </aside>
      </div>
    </div>
  );
}
