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
  "group flex min-h-16 w-full items-center justify-between gap-4 rounded-2xl bg-surface p-4 sm:p-5 text-left border border-border/80 shadow-card-modern hover:border-action/40 hover:shadow-card-hover hover:translate-y-[-1px] transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

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
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-emerald-500/10 via-teal-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <div className="flex flex-col gap-1 relative z-10">
          <h1 className="text-2xl sm:text-3xl font-heading font-extrabold tracking-tight text-primary">{t("knowledge.title")}</h1>
          <p className="text-sm text-secondary max-w-xl">{t("knowledge.intro")}</p>
        </div>
        <div className="relative z-10 shrink-0">
          <Button variant="secondary" onClick={() => setPasting(true)} data-testid="open-paste-extract" className="gap-2 shadow-xs">
            {t("extract.open")}
          </Button>
        </div>
      </div>

      {loadError ? <ErrorMessage error={loadError} /> : null}
      {template.isPending || facts.isPending ? (
        <p role="status" className="text-sm text-secondary">{t("common.loading")}</p>
      ) : null}

      {readiness.data ? (
        <Card className="flex flex-col gap-3 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern">
          <div className="flex items-center justify-between border-b border-border/60 pb-3">
            <h2 className="text-base font-heading font-bold text-primary">{t("readiness.title")}</h2>
          </div>
          <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} />
        </Card>
      ) : null}

      {pasting ? <PasteExtractSheet onClose={() => setPasting(false)} /> : null}

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
            <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-bold text-amber-800 border border-amber-500/30">
              {pending}
            </span>
          ) : null}
          <ChevronRightIcon className="shrink-0 text-xl text-secondary/50 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
        </div>
      </Link>

      <ul className="flex flex-col gap-3" aria-label={t("knowledge.categories")}>
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
  );
}
