import { useTranslation } from "react-i18next";
import type { Readiness } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, ChevronDownIcon, ShieldCheckIcon } from "@/components/icons";
import { FOCUS, Panel, PanelHeading, SkeletonRows } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import type { AppError } from "@/api/errors";
import { ReadinessChecklist } from "./ReadinessChecklist";

const LEVEL_TONE = {
  not_ready: "bg-danger-subtle text-danger",
  ready_for_drafts: "bg-attention-subtle text-attention",
  ready: "bg-success-subtle text-success",
} as const;

const STAGES = ["drafts", "ready"] as const;

/**
 * Readiness as the server computes it (essentials for drafts, then for automation), kept apart
 * from knowledge completeness: optional facts never appear here and never block anything.
 */
export function SetupPanel({ readiness, error }: { readiness: Readiness | undefined; error: AppError | null }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();

  return (
    <Panel aria-labelledby="knowledge-setup-title" data-testid="knowledge-setup" className="gap-3">
      <PanelHeading
        id="knowledge-setup-title"
        icon={<ShieldCheckIcon />}
        title={t("knowledge.setup.title")}
        wrap
        action={
          readiness ? (
            <span
              data-testid="knowledge-setup-level"
              data-level={readiness.level}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${LEVEL_TONE[readiness.level]}`}
            >
              {t(`readiness.level.${readiness.level}`)}
            </span>
          ) : undefined
        }
      />
      {error ? <ErrorMessage error={error} /> : null}
      {!readiness && !error ? <SkeletonRows label={t("common.loading")} rows={2} /> : null}
      {readiness ? (
        <>
          <p className="text-metadata text-secondary">{t(`knowledge.setup.level.${readiness.level}`)}</p>
          <div className="flex flex-col gap-2">
            {STAGES.map((stage) => {
              const requirements = readiness.requirements.filter((r) => r.required_for === stage);
              if (requirements.length === 0) return null;
              const open = requirements.filter((r) => !r.satisfied);
              const openKnowledge = open.filter((r) => r.link.target === "knowledge");
              const openOther = open.filter((r) => r.link.target !== "knowledge");
              const done = requirements.length - open.length;
              const complete = open.length === 0;
              const satisfied = (
                <div className="-mx-3">
                  <ReadinessChecklist
                    workspaceId={workspace.id}
                    readiness={{ ...readiness, requirements: requirements.filter((r) => r.satisfied) }}
                  />
                </div>
              );
              if (complete) {
                // A finished stage is one quiet row; its steps stay one click away.
                return (
                  <details key={stage} data-stage={stage} className="group rounded-xl bg-surface-subtle/60 px-3">
                    <summary className={`flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-xl select-none ${FOCUS}`}>
                      <span className="text-metadata font-semibold text-primary">{t(`knowledge.setup.stage.${stage}`)}</span>
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-success tabular-nums">
                        <CheckIcon aria-hidden="true" />
                        {t("readiness.progress", { done, total: requirements.length })}
                        <ChevronDownIcon aria-hidden="true" className="ml-0.5 text-sm text-secondary transition-transform group-open:rotate-180" />
                      </span>
                    </summary>
                    <div className="pb-2">{satisfied}</div>
                  </details>
                );
              }
              return (
                <section key={stage} aria-labelledby={`setup-${stage}`} className="rounded-xl bg-surface-subtle/60 px-3 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <h3 id={`setup-${stage}`} className="text-metadata font-semibold text-primary">
                      {t(`knowledge.setup.stage.${stage}`)}
                    </h3>
                    <span className="text-xs font-semibold text-secondary tabular-nums">
                      {t("readiness.progress", { done, total: requirements.length })}
                    </span>
                  </div>
                  {/* Knowledge gaps are already itemised under "Needs your attention"; only point there. */}
                  {openKnowledge.length > 0 ? (
                    <a
                      href="#knowledge-attention"
                      className={`mt-1.5 flex items-start gap-2 rounded-lg text-metadata text-attention hover:underline ${FOCUS}`}
                    >
                      <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
                      <span>{t("knowledge.setup.knowledgeOpen", { count: openKnowledge.length })}</span>
                    </a>
                  ) : null}
                  {openOther.length > 0 ? (
                    <div className="-mx-3 mt-1">
                      <ReadinessChecklist workspaceId={workspace.id} readiness={{ ...readiness, requirements: openOther }} />
                    </div>
                  ) : null}
                  {done > 0 ? (
                    <details className="group mt-0.5">
                      <summary className="flex min-h-11 cursor-pointer items-center text-xs font-medium text-secondary select-none hover:text-primary">
                        {t("core.completedRequirements", { count: done })}
                      </summary>
                      {satisfied}
                    </details>
                  ) : null}
                </section>
              );
            })}
          </div>
          <p className="text-xs leading-5 text-secondary">{t("knowledge.setup.note")}</p>
        </>
      ) : null}
    </Panel>
  );
}
