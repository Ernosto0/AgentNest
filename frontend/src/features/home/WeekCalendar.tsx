import { useTranslation } from "react-i18next";
import { PlusIcon } from "@/components/icons";
import type { ScheduledDay } from "./hooks";

/**
 * Seven days from today on the workspace clock. Each day shows how many posts and stories are
 * scheduled; a day without a story offers to draft one (the sheet does not take a date).
 */
export function WeekCalendar({ days, onDraftStory }: { days: ScheduledDay[]; onDraftStory: () => void }) {
  const { t, i18n } = useTranslation();

  return (
    <div className="flex flex-col gap-2">
      <ol data-testid="week-strip" className="grid grid-cols-7 gap-1 sm:gap-1.5">
        {days.map((day) => {
          const date = new Date(`${day.dayStr}T12:00:00Z`);
          const weekday = date.toLocaleDateString(i18n.language, { weekday: "short", timeZone: "UTC" });
          const dayNumber = date.toLocaleDateString(i18n.language, { day: "numeric", timeZone: "UTC" });
          const fullDate = date.toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
          const empty = day.total === 0;

          return (
            <li
              key={day.dayStr}
              data-testid={`week-day-${day.dayStr}`}
              aria-current={day.isToday ? "date" : undefined}
              className={`group/day relative flex min-w-0 flex-col items-center gap-0.5 rounded-xl border px-0.5 pt-1.5 pb-1 text-center transition-colors has-[button:focus-visible]:outline-2 has-[button:focus-visible]:outline-offset-2 has-[button:focus-visible]:outline-focus ${
                day.isToday
                  ? "border-action bg-action text-on-action"
                  : empty
                    ? "border-dashed border-border bg-transparent hover:border-action/40 hover:bg-surface-subtle/60"
                    : `border-transparent bg-surface-subtle ${day.hasStoryGap ? "hover:border-action/30" : ""}`
              }`}
            >
              {/* The full date is announced below; these visible labels are for sighted readers. */}
              <span
                aria-hidden="true"
                className={`w-full truncate text-[0.6875rem] font-semibold uppercase tracking-wide ${
                  day.isToday ? "text-on-action/85" : "text-secondary"
                }`}
              >
                {day.isToday ? (
                  <>
                    <span className="sm:hidden">{weekday}</span>
                    <span className="hidden sm:inline">{t("home.week.today")}</span>
                  </>
                ) : (
                  weekday
                )}
              </span>
              <span
                aria-hidden="true"
                className={`font-heading text-lg leading-6 font-bold tabular-nums ${
                  day.isToday ? "text-on-action" : empty ? "text-secondary/80" : "text-primary"
                }`}
              >
                {dayNumber}
              </span>
              <span className="sr-only">
                {day.isToday ? `${t("home.week.today")}, ` : ""}
                {fullDate}: {t("home.week.dayCounts", { posts: day.posts.length, stories: day.stories.length })}
              </span>
              <span aria-hidden="true" className="flex h-5 items-center justify-center gap-0.5">
                {day.posts.length > 0 ? (
                  <Count value={day.posts.length} className={day.isToday ? "bg-on-action text-action" : "bg-action text-on-action"} />
                ) : null}
                {day.stories.length > 0 ? <Count value={day.stories.length} className="bg-chart-2 text-primary" /> : null}
              </span>
              {day.hasStoryGap ? (
                <button
                  type="button"
                  onClick={onDraftStory}
                  title={t("home.week.gapAction")}
                  aria-label={`${fullDate}: ${t("home.week.gapAction")}`}
                  className={`flex size-7 items-center justify-center rounded-full outline-none transition-colors after:absolute after:inset-0 after:rounded-xl after:content-[''] ${
                    day.isToday
                      ? "text-on-action/80 group-hover/day:bg-on-action/15 group-hover/day:text-on-action"
                      : "text-secondary/70 group-hover/day:bg-surface group-hover/day:text-action"
                  }`}
                >
                  <PlusIcon className="text-base transition-transform group-hover/day:scale-110" />
                </button>
              ) : (
                <span aria-hidden="true" className="size-7" />
              )}
            </li>
          );
        })}
      </ol>
      <div aria-hidden="true" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-secondary">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-action" />
          {t("home.upNext.posts")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-chart-2" />
          {t("home.upNext.stories")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <PlusIcon className="text-xs" />
          {t("home.week.gapLegend")}
        </span>
      </div>
    </div>
  );
}

function Count({ value, className }: { value: number; className: string }) {
  return (
    <span className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[0.6875rem] font-bold tabular-nums ${className}`}>
      {value}
    </span>
  );
}
