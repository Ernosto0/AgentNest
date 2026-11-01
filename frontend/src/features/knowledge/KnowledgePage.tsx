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
  "flex min-h-14 w-full items-center justify-between gap-3 rounded-panel bg-surface p-4 text-left text-base border border-border shadow-xs hover:border-border-hover transition-colors focus-visible:outline-2 focus-visible:outline-focus";

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
    <div className="flex flex-col gap-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("knowledge.title")}</h1>
        <p className="mt-1 text-sm text-secondary">{t("knowledge.intro")}</p>
      </div>

      {loadError ? <ErrorMessage error={loadError} /> : null}
      {template.isPending || facts.isPending ? (
        <p role="status" className="text-sm text-secondary">{t("common.loading")}</p>
      ) : null}

      {readiness.data ? (
        <Card className="flex flex-col gap-3">
          <h2 className="text-lg font-heading font-semibold text-primary">{t("readiness.title")}</h2>
          <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} />
        </Card>
      ) : null}

      <div>
        <Button variant="secondary" onClick={() => setPasting(true)} data-testid="open-paste-extract">
          {t("extract.open")}
        </Button>
      </div>
      {pasting ? <PasteExtractSheet onClose={() => setPasting(false)} /> : null}

      <Link to={`${base}/suggestions`} className={ROW}>
        <span className="min-w-0">
          <span className="block font-medium text-primary">{t("knowledge.suggestions.link")}</span>
          <span className="block text-sm text-secondary">
            {pending > 0
              ? t("knowledge.suggestions.waiting", { count: pending })
              : t("knowledge.suggestions.none")}
          </span>
        </span>
        <ChevronRightIcon className="shrink-0 text-xl text-muted" />
      </Link>

      <ul className="flex flex-col gap-3" aria-label={t("knowledge.categories")}>
        {summaries.map((summary) => (
          <li key={summary.category}>
            <Link to={`${base}/${summary.category}`} className={ROW} data-category={summary.category}>
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-primary">{t(`knowledge.category.${summary.category}`)}</span>
                <span className="mt-1.5 flex flex-wrap gap-2">
                  {summary.verified > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary">
                      <FactStatusChip state="verified" />
                      <span>{summary.verified}</span>
                    </span>
                  ) : null}
                  {summary.attention > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary">
                      <FactStatusChip state="unverified" />
                      <span>{summary.attention}</span>
                    </span>
                  ) : null}
                  {summary.missing > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-secondary">
                      <FactStatusChip state="missing" />
                      <span>{summary.missing}</span>
                    </span>
                  ) : null}
                </span>
              </span>
              <ChevronRightIcon className="shrink-0 text-xl text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
