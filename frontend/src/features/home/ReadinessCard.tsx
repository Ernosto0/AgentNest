import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ReadinessChecklist } from "@/features/knowledge/ReadinessChecklist";
import { useReadiness } from "@/features/knowledge/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const LEVEL_TONE = {
  not_ready: "bg-danger-subtle text-danger border border-danger/40",
  ready_for_drafts: "bg-attention-subtle text-attention border border-attention/40",
  ready: "bg-success-subtle text-success border border-success/40",
} as const;

/** Readiness level plus what is still open, with deep links (AC-A1). */
export function ReadinessCard() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const readiness = useReadiness(workspace.id);

  const isReady = readiness.data?.level === "ready";
  const satisfiedCount = readiness.data?.requirements.filter((r) => r.satisfied).length ?? 0;
  const totalCount = readiness.data?.requirements.length ?? 0;
  const percentage = totalCount > 0 ? Math.round((satisfiedCount / totalCount) * 100) : 0;

  return (
    <Card className="flex flex-col gap-4 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern" aria-labelledby="readiness-title">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <h2 id="readiness-title" className="type-section font-heading font-bold tracking-tight text-primary text-base sm:text-lg">
          {t("readiness.title")}
        </h2>
        {readiness.data ? (
          <span
            data-testid="readiness-level"
            data-level={readiness.data.level}
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-bold tracking-wide shadow-2xs ${LEVEL_TONE[readiness.data.level]}`}
          >
            {t(`readiness.level.${readiness.data.level}`)}
          </span>
        ) : null}
      </div>
      {readiness.isPending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
      {readiness.isError ? <ErrorMessage error={readiness.error} /> : null}
      {readiness.data ? (
        <>
          <div className="flex flex-col gap-2.5 bg-surface-subtle/50 rounded-xl p-3.5 border border-border/60">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-secondary">
                {t("readiness.progress", {
                  done: satisfiedCount,
                  total: totalCount,
                })}
              </p>
              <span className="text-sm font-extrabold text-primary font-mono">{percentage}%</span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={satisfiedCount}
              aria-valuemin={0}
              aria-valuemax={totalCount}
              aria-label={t("readiness.title")}
              className="h-2.5 w-full overflow-hidden rounded-full bg-border/60"
            >
              <div
                className={`h-full rounded-full transition-all duration-normal shadow-xs ${
                  isReady ? "bg-emerald-600" : "bg-action"
                }`}
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
          {!isReady ? (
            <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} onlyOpen />
          ) : null}
          <div className="pt-1">
            <Link
              to={`/w/${workspace.id}/more/knowledge`}
              className="inline-flex min-h-11 items-center font-semibold text-action underline underline-offset-4 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus transition-colors text-sm"
            >
              {t("readiness.openKnowledge")}
            </Link>
          </div>
        </>
      ) : null}
    </Card>
  );
}
