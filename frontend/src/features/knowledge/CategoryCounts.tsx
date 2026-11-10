import { useTranslation } from "react-i18next";
import { STATE_PRESENTATION, TONE_TEXT, type ChipState } from "./presentation";
import type { CategorySummary } from "./model";

type Part = { state: ChipState; text: string };

/** The counts that matter for one category, worded, most urgent first. */
function parts(summary: CategorySummary, t: (key: string, options?: Record<string, unknown>) => string): Part[] {
  const list: Part[] = [];
  if (summary.needed.length > 0) list.push({ state: "needed", text: t("knowledge.count.needed") });
  if (summary.review > 0) list.push({ state: "unverified", text: t("knowledge.count.review", { count: summary.review }) });
  if (summary.verified > 0) list.push({ state: "verified", text: t("knowledge.count.verified", { count: summary.verified }) });
  if (summary.upcoming > 0) list.push({ state: "not_started", text: t("knowledge.count.upcoming", { count: summary.upcoming }) });
  if (summary.notAdded > 0 && summary.needed.length === 0) {
    list.push({ state: "not_added", text: t("knowledge.count.notAdded", { count: summary.notAdded }) });
  }
  return list;
}

/**
 * `line`: every count with its icon and word (tiles, headers).
 * `mark`: one compact signal for the category rail: what needs the owner, else the verified count.
 */
export function CategoryCounts({ summary, variant = "line" }: { summary: CategorySummary; variant?: "line" | "mark" }) {
  const { t } = useTranslation();
  const list = parts(summary, t);

  if (variant === "mark") {
    const first = list.find((part) => part.state === "needed" || part.state === "unverified" || part.state === "verified");
    if (!first) return null;
    const { icon: Icon, tone } = STATE_PRESENTATION[first.state];
    const value =
      first.state === "unverified" ? summary.review : first.state === "verified" ? summary.verified : null;
    return (
      <span className={`inline-flex shrink-0 items-center gap-1 text-xs font-semibold tabular-nums ${tone === "neutral" ? "text-secondary/70" : TONE_TEXT[tone]}`}>
        <Icon aria-hidden="true" className="text-[0.8125rem]" />
        {value !== null ? <span aria-hidden="true">{value}</span> : null}
        <span className="sr-only">{first.text}</span>
      </span>
    );
  }

  if (list.length === 0) {
    return <span className="truncate text-xs leading-5 text-secondary">{t("knowledge.count.empty")}</span>;
  }
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs leading-5">
      {list.map((part) => {
        const { icon: Icon, tone } = STATE_PRESENTATION[part.state];
        return (
          <span key={part.state} data-count={part.state} className={`inline-flex items-center gap-1 whitespace-nowrap ${part.state === "needed" ? "font-semibold" : "font-medium"} ${TONE_TEXT[tone]}`}>
            <Icon aria-hidden="true" className="text-[0.8125rem]" />
            {part.text}
          </span>
        );
      })}
    </span>
  );
}
