import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { FOCUS } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { knowledgeBase } from "./useKnowledgeBase";
import type { Overview } from "./model";

type Cell = {
  id: "verified" | "review" | "suggestions" | "notAdded";
  value: number;
  hint: string;
  tone: "neutral" | "attention";
  to?: string;
};

/**
 * What the assistant knows, in four real counts: verified facts in use, facts waiting for the
 * owner, suggestions to decide and checklist items not added yet (with how many block setup).
 * No percentage: an optional FAQ is not "incomplete knowledge".
 */
export function KnowledgeStats({ data }: { data: Overview | null }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();

  const cells: Cell[] = data
    ? [
        { id: "verified", value: data.verified, hint: t("knowledge.stats.verifiedHint"), tone: "neutral" },
        {
          id: "review",
          value: data.review,
          hint: data.review > 0 ? t("knowledge.stats.reviewHint") : t("knowledge.stats.none"),
          tone: data.review > 0 ? "attention" : "neutral",
        },
        {
          id: "suggestions",
          value: data.suggestions,
          hint: data.suggestions > 0 ? t("knowledge.stats.suggestionsHint") : t("knowledge.stats.none"),
          tone: data.suggestions > 0 ? "attention" : "neutral",
          to: `${knowledgeBase(workspace.id)}/suggestions`,
        },
        {
          id: "notAdded",
          value: data.notAdded,
          hint:
            data.needed > 0
              ? t("knowledge.stats.neededHint", { count: data.needed })
              : data.notAdded > 0
                ? t("knowledge.stats.optionalHint")
                : t("knowledge.stats.none"),
          tone: data.needed > 0 ? "attention" : "neutral",
        },
      ]
    : [];

  return (
    <section
      aria-labelledby="knowledge-stats-title"
      data-testid="knowledge-stats"
      className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface lg:flex-row"
    >
      <div className="flex min-w-0 flex-col justify-center gap-0.5 px-5 pt-3 pb-2.5 lg:w-56 lg:shrink-0 lg:border-r lg:border-border lg:py-3 xl:w-64">
        <h2 id="knowledge-stats-title" className="font-heading text-base font-semibold tracking-tight text-primary">
          {t("knowledge.stats.title")}
        </h2>
        <p className="text-xs text-secondary">{t("knowledge.stats.subtitle")}</p>
      </div>
      {data ? (
        <dl className="grid flex-1 grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 lg:border-t-0">
          {cells.map((cell) => {
            const label = t(`knowledge.stats.${cell.id}`);
            const attention = cell.tone === "attention";
            const number = (
              <span className={cell.value === 0 ? "text-secondary" : attention ? "text-attention" : "text-primary"}>
                {cell.value}
              </span>
            );
            return (
              <div
                key={cell.id}
                data-testid={`knowledge-stat-${cell.id}`}
                className={`relative flex min-w-0 flex-col justify-center bg-surface px-5 py-3 ${cell.to ? "transition-colors hover:bg-surface-subtle/70" : ""}`}
              >
                <dt className="truncate text-xs font-medium text-secondary">{label}</dt>
                <dd className="font-heading text-[1.625rem] leading-8 font-bold tracking-tight tabular-nums">
                  {cell.to ? (
                    <Link
                      to={cell.to}
                      aria-label={`${label}: ${cell.value}`}
                      className={`rounded-control after:absolute after:inset-0 after:content-[''] ${FOCUS}`}
                    >
                      {number}
                    </Link>
                  ) : (
                    number
                  )}
                </dd>
                <dd className={`line-clamp-2 text-[0.6875rem] leading-tight font-medium ${attention ? "text-attention" : "text-secondary"}`}>
                  {cell.hint}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <div role="status" className="grid flex-1 grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 lg:border-t-0">
          <span className="sr-only">{t("common.loading")}</span>
          {[0, 1, 2, 3].map((key) => (
            <div key={key} aria-hidden="true" className="flex flex-col gap-2 bg-surface px-5 py-3.5">
              <div className="h-2.5 w-20 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
              <div className="h-6 w-10 rounded-md bg-surface-subtle motion-safe:animate-pulse" />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
