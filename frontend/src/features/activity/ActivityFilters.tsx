import { useTranslation } from "react-i18next";
import { XIcon } from "@/components/icons";
import { FOCUS } from "@/features/home/DashboardPanel";
import { dayLabel } from "@/features/reports/dates";
import { ACTIVITY_GROUPS, OUTCOMES, isOutcome, type ActivityFilters as Filters, type ActivityGroup } from "./hooks";

const CONTROL = `min-h-11 rounded-control border border-border bg-surface px-3 text-body text-primary ${FOCUS}`;

/**
 * Every control maps to a server-side filter, so a filtered feed is the complete history for that
 * choice, never a filter over the loaded page.
 */
export function ActivityFilters({
  filters,
  today,
  onChange,
  onClear,
}: {
  filters: Filters;
  today: string;
  onChange: (patch: Partial<Filters>) => void;
  onClear: () => void;
}) {
  const { t, i18n } = useTranslation();
  const narrowed = filters.group !== null || filters.outcome !== null || filters.day !== null;

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid="activity-filters">
      <div
        role="group"
        aria-label={t("activity.filterLabel")}
        className="-mx-4 flex min-w-0 gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:thin] md:mx-0 md:flex-wrap md:overflow-visible md:px-0 md:pb-0"
      >
        {[null, ...ACTIVITY_GROUPS].map((name: ActivityGroup | null) => {
          const active = filters.group === name;
          return (
            <button
              key={name ?? "all"}
              type="button"
              aria-pressed={active}
              onClick={() => onChange({ group: name })}
              className={`inline-flex min-h-10 shrink-0 items-center rounded-full border px-3.5 text-metadata font-semibold whitespace-nowrap transition-colors duration-150 ${FOCUS} ${
                active
                  ? "border-action bg-action text-on-action"
                  : "border-border bg-surface text-secondary hover:border-action/40 hover:text-primary"
              }`}
            >
              {name ? t(`activity.groups.${name}`) : t("activity.groups.all")}
            </button>
          );
        })}
      </div>

      <div className="flex min-w-0 flex-wrap items-end gap-x-3 gap-y-2.5">
        <label className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-semibold text-secondary">{t("activity.filters.outcome")}</span>
          <select
            value={filters.outcome ?? ""}
            onChange={(event) => onChange({ outcome: isOutcome(event.target.value) ? event.target.value : null })}
            className={`${CONTROL} pr-8`}
          >
            <option value="">{t("activity.filters.outcomeAll")}</option>
            {OUTCOMES.map((outcome) => (
              <option key={outcome} value={outcome}>
                {t(`activity.filters.outcomes.${outcome}`)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor="activity-day" className="text-xs font-semibold text-secondary">
            {t("activity.filters.day")}
          </label>
          <div className="flex items-center gap-1">
            <input
              id="activity-day"
              type="date"
              max={today}
              value={filters.day ?? ""}
              onChange={(event) => onChange({ day: event.target.value || null })}
              className={CONTROL}
            />
            {filters.day ? (
              <button
                type="button"
                onClick={() => onChange({ day: null })}
                aria-label={t("activity.filters.clearDay")}
                className={`inline-flex size-11 items-center justify-center rounded-control text-secondary hover:bg-surface-subtle hover:text-primary ${FOCUS}`}
              >
                <XIcon />
              </button>
            ) : null}
          </div>
        </div>

        <button
          type="button"
          aria-pressed={filters.technical}
          onClick={() => onChange({ technical: !filters.technical })}
          className={`ml-auto inline-flex min-h-11 items-center gap-2.5 rounded-control px-2 text-metadata font-medium text-secondary hover:text-primary ${FOCUS}`}
        >
          <span
            aria-hidden="true"
            className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors motion-reduce:transition-none ${filters.technical ? "bg-action" : "bg-border"}`}
          >
            <span
              className={`absolute top-0.5 size-4 rounded-full bg-surface shadow-xs transition-transform motion-reduce:transition-none ${filters.technical ? "translate-x-4.5" : "translate-x-0.5"}`}
            />
          </span>
          {t("activity.filters.technical")}
        </button>
      </div>

      {narrowed ? (
        <div role="status" className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-metadata text-secondary" data-testid="activity-active-filters">
          <span className="min-w-0">
            {t("activity.filters.showing", {
              what: [
                filters.outcome ? t(`activity.filters.outcomes.${filters.outcome}`) : null,
                filters.group ? t(`activity.groups.${filters.group}`) : null,
                filters.day ? dayLabel(filters.day, i18n.language) : null,
              ]
                .filter(Boolean)
                .join(" · "),
            })}
          </span>
          <button type="button" onClick={onClear} className={`-mx-1 inline-flex min-h-9 items-center rounded-control px-1 font-semibold text-action hover:text-action-hover hover:underline ${FOCUS}`}>
            {t("activity.filters.clear")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
