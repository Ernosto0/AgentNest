import { PageHeader } from "@/components/Layout";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { FactCandidate } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCandidates, useResolveCandidate } from "./hooks";
import { pickLabel } from "./labels";

/** Pending suggestions: staff proposals (contest) and values found elsewhere (discrepancy, new). */
export function SuggestionsPage() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const canVerify = role !== "staff";
  const candidates = useCandidates(workspace.id);
  const resolve = useResolveCandidate(workspace.id);

  const explain = (candidate: FactCandidate): string => {
    const params = {
      proposed: candidate.proposed_display,
      current: candidate.current_display ?? "",
      name: candidate.proposed_by_name ?? t("knowledge.suggestions.someone"),
      source: t(`knowledge.candidateSource.${candidate.source_type}`, {
        defaultValue: candidate.source_type,
      }),
    };
    if (candidate.relation === "contest") return t("knowledge.suggestions.relation.contest", params);
    if (candidate.relation === "discrepancy") return t("knowledge.suggestions.relation.discrepancy", params);
    return candidate.current_display
      ? t("knowledge.suggestions.relation.newUnverified", params)
      : t("knowledge.suggestions.relation.new", params);
  };

  const busy = (id: string) => resolve.isPending && resolve.variables?.candidateId === id;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          to={`/w/${workspace.id}/more/knowledge`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-action hover:underline focus-visible:outline-2 focus-visible:outline-focus"
        >
          {t("knowledge.back")}
        </Link>
        <PageHeader title={t("knowledge.suggestions.title")} description={t("knowledge.suggestions.intro")} />
      </div>

      {!canVerify ? (
        <p className="rounded-panel bg-surface-subtle p-4 text-sm text-secondary border border-border">{t("knowledge.suggestions.staffNote")}</p>
      ) : null}
      {candidates.isError ? <ErrorMessage error={candidates.error} /> : null}
      {resolve.error ? <ErrorMessage error={resolve.error} /> : null}
      {candidates.isPending ? <p className="text-secondary">{t("common.loading")}</p> : null}
      {candidates.data?.length === 0 ? (
        <EmptyState
          title={t("knowledge.suggestions.empty")}
          description={t("knowledge.suggestions.emptyHint")}
        />
      ) : null}

      <ul className="grid min-w-0 items-start gap-4 xl:grid-cols-2">
        {candidates.data?.map((candidate) => (
          <li key={candidate.id}>
            <Card className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-5 shadow-xs" data-testid={`candidate-${candidate.fact_key}`}>
              <div className="border-b border-border/60 pb-2">
                <h2 className="text-base font-semibold text-primary break-words">
                  {pickLabel(candidate.fact_label, i18n.language)}
                </h2>
              </div>
              <p className="text-base text-primary break-words font-medium">{explain(candidate)}</p>
              {candidate.source_excerpt ? (
                <blockquote className="rounded-control border-l-4 border-action bg-surface-subtle p-3 text-sm text-secondary italic">
                  {candidate.source_excerpt}
                </blockquote>
              ) : null}
              {canVerify ? (
                <div className="mt-1 flex flex-wrap gap-2 pt-2 border-t border-border/40">
                  <Button
                    disabled={busy(candidate.id)}
                    onClick={() => resolve.mutate({ candidateId: candidate.id, action: "accept" })}
                  >
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
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
