import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { FactCandidate } from "@/api/types";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronLeftIcon, SparkIcon, UsersIcon } from "@/components/icons";
import { PageHeader } from "@/components/Layout";
import { FOCUS, SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCandidates, useResolveCandidate } from "./hooks";
import { CategoryGlyph } from "./CategoryGlyph";
import { knowledgeBase } from "./useKnowledgeBase";
import { isCategory, pickLabel } from "./labels";
import { PasteExtractSheet } from "./PasteExtractSheet";

/**
 * Pending suggestions: staff proposals (contest) and values found elsewhere (discrepancy, new).
 * Each shows what is in use now beside what is proposed; nothing changes until the owner decides.
 */
export function SuggestionsPage() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canVerify = role !== "staff";
  const candidates = useCandidates(workspace.id);
  const resolve = useResolveCandidate(workspace.id);
  const [pasting, setPasting] = useState(false);

  const sourceOf = (candidate: FactCandidate) =>
    t(`knowledge.candidateSource.${candidate.source_type}`, { defaultValue: candidate.source_type });

  const explain = (candidate: FactCandidate): string => {
    const params = {
      proposed: candidate.proposed_display,
      current: candidate.current_display ?? "",
      name: candidate.proposed_by_name ?? t("knowledge.suggestions.someone"),
      source: sourceOf(candidate),
    };
    if (candidate.relation === "contest") return t("knowledge.suggestions.relation.contest", params);
    if (candidate.relation === "discrepancy") return t("knowledge.suggestions.relation.discrepancy", params);
    return candidate.current_display
      ? t("knowledge.suggestions.relation.newUnverified", params)
      : t("knowledge.suggestions.relation.new", params);
  };

  const busy = (id: string) => resolve.isPending && resolve.variables?.candidateId === id;
  const count = candidates.data?.length ?? 0;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="flex min-w-0 flex-col gap-3">
        <Link
          to={knowledgeBase(workspace.id)}
          className={`-ml-1 inline-flex min-h-11 items-center gap-1 self-start rounded-control px-1 text-metadata font-semibold text-action hover:text-action-hover ${FOCUS}`}
        >
          <ChevronLeftIcon aria-hidden="true" className="text-base" />
          {t("knowledge.back")}
        </Link>
        <PageHeader
          title={t("knowledge.suggestions.title")}
          description={t("knowledge.suggestions.intro")}
          action={
            <Button variant="secondary" onClick={() => setPasting(true)}>
              <SparkIcon className="text-base text-action" />
              {t("extract.open")}
            </Button>
          }
        />
      </div>

      {!canVerify ? (
        <p className="rounded-xl bg-surface-subtle px-4 py-3 text-metadata text-secondary">{t("knowledge.suggestions.staffNote")}</p>
      ) : null}
      {candidates.isError ? <ErrorMessage error={candidates.error} /> : null}
      {resolve.error ? <ErrorMessage error={resolve.error} /> : null}
      {candidates.isPending ? <SkeletonRows label={t("common.loading")} rows={3} /> : null}
      {candidates.data?.length === 0 ? (
        <EmptyState title={t("knowledge.suggestions.empty")} description={t("knowledge.suggestions.emptyHint")} />
      ) : null}
      {count > 0 ? <p className="-mb-2 text-xs text-secondary">{t("knowledge.suggestions.waiting", { count })}</p> : null}

      <ul className="grid min-w-0 items-start gap-3 xl:grid-cols-2">
        {candidates.data?.map((candidate) => {
          const category = candidate.fact_key.split(".")[0];
          const fromTeam = candidate.source_type === "staff_proposal";
          return (
            <li key={candidate.id} className="min-w-0">
              <article
                data-testid={`candidate-${candidate.fact_key}`}
                aria-labelledby={`candidate-${candidate.id}`}
                className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-surface p-4 sm:p-5"
              >
                <header className="flex min-w-0 items-start gap-3">
                  {isCategory(category) ? <CategoryGlyph category={category} size="sm" /> : null}
                  <div className="min-w-0 flex-1">
                    <h2 id={`candidate-${candidate.id}`} className="text-body leading-5 font-semibold [overflow-wrap:anywhere] text-primary">
                      {pickLabel(candidate.fact_label, i18n.language)}
                    </h2>
                    <p className="text-xs text-secondary">{isCategory(category) ? t(`knowledge.category.${category}`) : null}</p>
                  </div>
                  <span
                    className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 text-xs leading-5 font-semibold ${
                      fromTeam ? "bg-surface-subtle text-secondary" : "bg-assistant text-action"
                    }`}
                  >
                    {fromTeam ? <UsersIcon aria-hidden="true" /> : <SparkIcon aria-hidden="true" />}
                    {sourceOf(candidate)}
                  </span>
                </header>

                <dl className="grid min-w-0 gap-2 sm:grid-cols-2">
                  <div className="min-w-0 rounded-xl bg-surface-subtle/70 px-3 py-2">
                    <dt className="text-xs font-medium text-secondary">{t("knowledge.suggestions.current")}</dt>
                    <dd className="text-body font-medium [overflow-wrap:anywhere] whitespace-pre-line text-primary">
                      {candidate.current_display ?? <span className="text-secondary">{t("knowledge.suggestions.nothingYet")}</span>}
                    </dd>
                  </div>
                  <div className="min-w-0 rounded-xl border border-action/25 bg-assistant/40 px-3 py-2">
                    <dt className="text-xs font-medium text-action">{t("knowledge.suggestions.proposed")}</dt>
                    <dd className="text-body font-semibold [overflow-wrap:anywhere] whitespace-pre-line text-primary">{candidate.proposed_display}</dd>
                  </div>
                </dl>

                <p className="text-metadata [overflow-wrap:anywhere] text-secondary">{explain(candidate)}</p>
                {candidate.source_excerpt ? (
                  <blockquote className="rounded-r-lg border-l-2 border-action/40 bg-surface-subtle/60 px-3 py-2 text-metadata [overflow-wrap:anywhere] text-secondary italic">
                    {candidate.source_excerpt}
                  </blockquote>
                ) : null}
                {canVerify ? (
                  <div className="flex flex-wrap gap-2 border-t border-border/70 pt-3">
                    <Button disabled={busy(candidate.id)} onClick={() => resolve.mutate({ candidateId: candidate.id, action: "accept" })}>
                      {t("knowledge.suggestions.accept", { value: candidate.proposed_display })}
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={busy(candidate.id)}
                      onClick={() => resolve.mutate({ candidateId: candidate.id, action: "reject" })}
                    >
                      {t("knowledge.suggestions.reject")}
                    </Button>
                  </div>
                ) : null}
              </article>
            </li>
          );
        })}
      </ul>

      {pasting ? <PasteExtractSheet onClose={() => setPasting(false)} /> : null}
    </div>
  );
}
