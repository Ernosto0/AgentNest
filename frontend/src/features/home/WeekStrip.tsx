import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import type { ScheduledDay } from "./hooks";

export function WeekStrip({
  days,
  onGapClick,
}: {
  days: ScheduledDay[];
  onGapClick?: (dayStr: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex flex-col gap-2.5" data-testid="week-strip">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-secondary">
          {t("home.week.title")}
        </h3>
        <Link
          to={`/w/${workspace.id}/content?view=agenda`}
          className="text-xs font-semibold text-action hover:underline"
        >
          {t("home.week.viewDay")}
        </Link>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
        {days.map((day) => {
          const date = new Date(`${day.dayStr}T12:00:00Z`);
          const weekday = day.isToday
            ? t("home.week.today")
            : day.isTomorrow
            ? t("home.week.tomorrow")
            : date.toLocaleDateString(i18n.language, { weekday: "short" });
          const dayNumber = date.toLocaleDateString(i18n.language, { day: "numeric", month: "short" });

          return (
            <div
              key={day.dayStr}
              data-testid={`week-day-${day.dayStr}`}
              className={`flex flex-col justify-between rounded-control border p-2.5 transition-colors ${
                day.isToday
                  ? "border-action/40 bg-action-subtle/20"
                  : "border-border/60 bg-surface-subtle/40 hover:bg-surface-subtle"
              }`}
            >
              <div className="flex items-center justify-between gap-1 border-b border-border/40 pb-1.5">
                <span className={`text-xs font-bold ${day.isToday ? "text-action" : "text-primary"}`}>
                  {weekday}
                </span>
                <span className="text-[11px] font-medium text-secondary">{dayNumber}</span>
              </div>

              {/* Counts */}
              <div className="flex flex-col gap-1 py-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-secondary">{t("home.upNext.stories")}</span>
                  <span
                    className={`font-semibold ${
                      day.stories.length > 0 ? "text-primary font-mono" : "text-secondary/60"
                    }`}
                  >
                    {day.stories.length}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-secondary">{t("home.upNext.posts")}</span>
                  <span
                    className={`font-semibold ${
                      day.posts.length > 0 ? "text-primary font-mono" : "text-secondary/60"
                    }`}
                  >
                    {day.posts.length}
                  </span>
                </div>
              </div>

              {/* Gap warning or clean status */}
              {day.hasStoryGap ? (
                <button
                  type="button"
                  onClick={() => onGapClick?.(day.dayStr)}
                  className="mt-1 flex items-center justify-center rounded-control bg-attention-subtle px-1.5 py-1 text-[11px] font-semibold text-attention hover:bg-attention-subtle/80 transition-colors"
                  title={t("home.week.gap")}
                >
                  +{t("home.week.gap")}
                </button>
              ) : (
                <div className="mt-1 h-6 flex items-center justify-center">
                  <span className="inline-block size-1.5 rounded-full bg-success/70" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
