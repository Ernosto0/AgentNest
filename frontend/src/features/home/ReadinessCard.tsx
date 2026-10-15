import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ReadinessChecklist } from "@/features/knowledge/ReadinessChecklist";
import { useReadiness } from "@/features/knowledge/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

const LEVEL_TONE = {
  not_ready: "bg-orange-50 text-orange-900 ring-orange-400",
  ready_for_drafts: "bg-amber-50 text-amber-900 ring-amber-400",
  ready: "bg-green-50 text-green-900 ring-green-500",
} as const;

/** Readiness level plus what is still open, with deep links (AC-A1). */
export function ReadinessCard() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const readiness = useReadiness(workspace.id);

  return (
    <Card className="flex flex-col gap-3" aria-labelledby="readiness-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="readiness-title" className="text-lg font-medium">
          {t("readiness.title")}
        </h2>
        {readiness.data ? (
          <span
            data-testid="readiness-level"
            data-level={readiness.data.level}
            className={`inline-flex rounded-full px-2.5 py-1 text-sm font-medium ring-1 ring-inset ${LEVEL_TONE[readiness.data.level]}`}
          >
            {t(`readiness.level.${readiness.data.level}`)}
          </span>
        ) : null}
      </div>
      {readiness.isPending ? <p className="text-sm text-slate-600">{t("common.loading")}</p> : null}
      {readiness.isError ? <ErrorMessage error={readiness.error} /> : null}
      {readiness.data ? (
        <>
          <p className="text-sm text-slate-600">
            {t("readiness.progress", {
              done: readiness.data.requirements.filter((r) => r.satisfied).length,
              total: readiness.data.requirements.length,
            })}
          </p>
          <ReadinessChecklist workspaceId={workspace.id} readiness={readiness.data} onlyOpen />
          <Link
            to={`/w/${workspace.id}/more/knowledge`}
            className="inline-flex min-h-11 items-center font-medium text-indigo-800 underline focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            {t("readiness.openKnowledge")}
          </Link>
        </>
      ) : null}
    </Card>
  );
}
