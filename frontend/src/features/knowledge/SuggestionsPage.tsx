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
          className="inline-flex min-h-11 items-center text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
        >
          {t("knowledge.back")}
        </Link>
        <h1 className="text-2xl font-semibold">{t("knowledge.suggestions.title")}</h1>
        <p className="mt-1 text-slate-600">{t("knowledge.suggestions.intro")}</p>
      </div>

      {!canVerify ? (
        <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-800">{t("knowledge.suggestions.staffNote")}</p>
      ) : null}
      {candidates.isError ? <ErrorMessage error={candidates.error} /> : null}
      {resolve.error ? <ErrorMessage error={resolve.error} /> : null}
      {candidates.isPending ? <p>{t("common.loading")}</p> : null}
      {candidates.data?.length === 0 ? (
        <EmptyState
          title={t("knowledge.suggestions.empty")}
          description={t("knowledge.suggestions.emptyHint")}
        />
      ) : null}

      <ul className="flex flex-col gap-3">
        {candidates.data?.map((candidate) => (
          <li key={candidate.id}>
            <Card className="flex flex-col gap-2" data-testid={`candidate-${candidate.fact_key}`}>
              <h2 className="text-base font-semibold break-words">
                {pickLabel(candidate.fact_label, i18n.language)}
              </h2>
              <p className="text-base break-words">{explain(candidate)}</p>
              {candidate.source_excerpt ? (
                <blockquote className="border-l-4 border-slate-300 pl-3 text-sm text-slate-700">
                  {candidate.source_excerpt}
                </blockquote>
              ) : null}
              {canVerify ? (
                <div className="mt-1 flex flex-wrap gap-2">
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
