import { useTranslation } from "react-i18next";
import type { ActivitySummary } from "@/api/types";
import { FOCUS } from "@/features/home/DashboardPanel";
import { SUMMARY_DAYS, type Outcome } from "./hooks";

type Tile = { id: Outcome | null; label: string; value: number; tone: "neutral" | "success" | "attention" | "danger"; hint?: string };

const VALUE_TONE = {
  neutral: "text-primary",
  success: "text-success",
  attention: "text-attention",
  danger: "text-danger",
} as const;

/**
 * Recent activity at a glance (server counts over the whole history of the last local days, not
 * the loaded page). Each count also filters the feed below by that outcome; "Key events" clears it.
 */
export function ActivitySummaryStrip({
  summary,
  pending,
  failed,
  outcome,
  onOutcome,
}: {
  summary: ActivitySummary | undefined;
  pending: boolean;
  failed: boolean;
  outcome: Outcome | null;
  onOutcome: (next: Outcome | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const number = (n: number) => n.toLocaleString(i18n.language);

  const tiles: Tile[] = summary
    ? [
        {
          id: null,
          label: t("activity.summary.total"),
          value: summary.total,
          tone: "neutral",
          hint: summary.routine > 0 ? t("activity.summary.routine", { count: summary.routine, value: number(summary.routine) }) : undefined,
        },
        { id: "success", label: t("activity.summary.success"), value: summary.success, tone: summary.success > 0 ? "success" : "neutral" },
        { id: "warning", label: t("activity.summary.warning"), value: summary.warning, tone: summary.warning > 0 ? "attention" : "neutral" },
        { id: "failure", label: t("activity.summary.failure"), value: summary.failure, tone: summary.failure > 0 ? "danger" : "neutral" },
      ]
    : [];

  return (
    <section
      aria-labelledby="activity-summary-title"
      data-testid="activity-summary"
      className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface lg:flex-row"
    >
      <div className="flex min-w-0 flex-col justify-center gap-0.5 px-5 pt-3 pb-2.5 lg:w-56 lg:shrink-0 lg:border-r lg:border-border lg:py-3 xl:w-64">
        <h2 id="activity-summary-title" className="font-heading text-base font-semibold tracking-tight text-primary">
          {t("activity.summary.title", { count: SUMMARY_DAYS })}
        </h2>
        <p className="text-xs leading-5 text-secondary">{t("activity.summary.scope")}</p>
      </div>
      {failed ? (
        <p role="status" className="flex-1 px-5 py-4 text-metadata text-secondary">
          {t("activity.summary.unavailable")}
        </p>
      ) : pending || !summary ? (
        <div role="status" className="grid flex-1 grid-cols-2 gap-px bg-border sm:grid-cols-4">
          <span className="sr-only">{t("common.loading")}</span>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} aria-hidden="true" className="flex flex-col gap-2 bg-surface px-5 py-3.5">
              <div className="h-2.5 w-16 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
              <div className="h-6 w-10 rounded-md bg-surface-subtle motion-safe:animate-pulse" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="grid flex-1 grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 lg:border-t-0">
          {tiles.map((tile) => {
            const active = tile.id === outcome;
            return (
              <li key={tile.id ?? "all"} className="flex min-w-0 bg-surface">
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => onOutcome(active ? null : tile.id)}
                  data-testid={`activity-summary-${tile.id ?? "total"}`}
                  className={`group flex min-h-[4.5rem] w-full min-w-0 flex-col items-start justify-center gap-0.5 px-5 py-3 text-left transition-colors hover:bg-surface-subtle/60 ${FOCUS} focus-visible:-outline-offset-2 ${
                    active ? "bg-surface-subtle shadow-[inset_0_-2px_0_var(--color-action)]" : ""
                  }`}
                >
                  <span className="text-metadata font-medium text-secondary">{tile.label}</span>
                  <span className={`font-heading text-2xl leading-tight font-semibold tabular-nums ${tile.value === 0 ? "text-secondary/70" : VALUE_TONE[tile.tone]}`}>
                    {number(tile.value)}
                  </span>
                  {tile.hint ? <span className="text-xs leading-4 text-secondary">{tile.hint}</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
