import { useTranslation } from "react-i18next";
import { ErrorMessage } from "@/components/ErrorMessage";
import { BookIcon } from "@/components/icons";
import { ReadinessChecklist } from "@/features/knowledge/ReadinessChecklist";
import { useReadiness } from "@/features/knowledge/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";

const LEVEL_TONE = {
  not_ready: "bg-danger-subtle text-danger",
  ready_for_drafts: "bg-attention-subtle text-attention",
  ready: "bg-success-subtle text-success",
} as const;

/** Readiness level plus what is still open, with deep links (AC-A1). Hidden when complete. */
export function ReadinessCard() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const readiness = useReadiness(workspace.id);

  const isReady = readiness.data?.level === "ready";
  const satisfiedCount = readiness.data?.requirements.filter((r) => r.satisfied).length ?? 0;
  const totalCount = readiness.data?.requirements.length ?? 0;
  const percentage = totalCount > 0 ? Math.round((satisfiedCount / totalCount) * 100) : 0;

  if (isReady) return null;

  return (
    <Panel aria-labelledby="readiness-title" className="gap-4">
      <PanelHeading
        id="readiness-title"
        icon={<BookIcon />}
        title={t("readiness.title")}
        meta={t("home.readiness.subtitle")}
        action={
          readiness.data ? (
            <span
              data-testid="readiness-level"
              data-level={readiness.data.level}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${LEVEL_TONE[readiness.data.level]}`}
            >
              {t(`readiness.level.${readiness.data.level}`)}
            </span>
          ) : undefined
        }
      />
      {readiness.isPending ? <SkeletonRows label={t("common.loading")} rows={2} /> : null}
      {readiness.isError ? <ErrorMessage error={readiness.error} /> : null}
      {readiness.data ? (
        <>
          <div className="flex items-center gap-3">
            <div
              role="progressbar"
              aria-valuenow={satisfiedCount}
              aria-valuemin={0}
              aria-valuemax={totalCount}
              aria-label={t("readiness.title")}
              className="h-2 flex-1 overflow-hidden rounded-full bg-surface-subtle"
            >
              <div className="h-full rounded-full bg-action transition-[width] duration-normal" style={{ width: `${percentage}%` }} />
            </div>
            <p className="shrink-0 text-metadata font-semibold text-secondary tabular-nums">
              {t("readiness.progress", { done: satisfiedCount, total: totalCount })}
            </p>
          </div>
          <div className="-mx-3">
            <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} onlyOpen />
          </div>
          {satisfiedCount > 0 ? (
            <details className="group -mt-1">
              <summary className="min-h-11 cursor-pointer py-2 text-metadata font-medium text-secondary hover:text-primary">
                {t("core.completedRequirements", { count: satisfiedCount })}
              </summary>
              <div className="-mx-3">
                <ReadinessChecklist
                  workspaceId={workspace.id}
                  readiness={{ ...readiness.data, requirements: readiness.data.requirements.filter((r) => r.satisfied) }}
                />
              </div>
            </details>
          ) : null}
          <PanelLink to={`/w/${workspace.id}/more/knowledge`} className="self-start">
            {t("readiness.openKnowledge")}
          </PanelLink>
        </>
      ) : null}
    </Panel>
  );
}
