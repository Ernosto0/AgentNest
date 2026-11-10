import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon, ClockIcon, PencilIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { shiftDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import {
  buildWeek,
  coverageOf,
  earlierThan,
  friendlyMoment,
  groupByDay,
  itemDay,
  parseWeekParam,
  timeOfDay,
  weekRangeLabel,
  weekStartOf,
  type AgendaDay,
} from "./agenda";
import { ContentMedia } from "./ContentMedia";
import { TypePill } from "./ContentCard";
import { LIST_LIMIT, useContentItems } from "./hooks";
import { timezoneLabel } from "./messages";
import { textPreview } from "./presentation";
import { contentBadge, TAB_STATUSES } from "./status";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
/** How far ahead the week arrows go when nothing is scheduled later than that. */
const WEEKS_AHEAD = 8;

type Layout = "week" | "list";

/**
 * The schedule: a Monday-to-Sunday week on the workspace clock, or every scheduled item as one
 * list. Both show only what the scheduled list returned; when that list is a full page, days after
 * its last item are marked as not loaded instead of looking free.
 */
export function AgendaView({ draftCount, onWrite }: { draftCount: number; onWrite: () => void }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const timezone = workspace.timezone;
  const scheduled = useContentItems(workspace.id, "scheduled");
  const [params, setParams] = useSearchParams();
  const headingId = useId();

  const layout: Layout = params.get("layout") === "list" ? "list" : "week";
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const raw = scheduled.data ?? [];
  const items = raw.filter((item) => TAB_STATUSES.scheduled.includes(item.status));
  const coverage = coverageOf(raw, LIST_LIMIT, timezone);

  const today = todayIn(timezone);
  const currentWeek = weekStartOf(today);
  const lastItemDay = items.map((item) => itemDay(item, timezone)).filter((day): day is string => day !== null).sort().at(-1);
  const lastWeek = [shiftDay(currentWeek, WEEKS_AHEAD * 7), lastItemDay ? weekStartOf(lastItemDay) : currentWeek].sort().at(-1)!;
  const requested = parseWeekParam(params.get("week")) ?? currentWeek;
  const week = requested < currentWeek ? currentWeek : requested > lastWeek ? lastWeek : requested;
  const goWeek = (start: string) => setParam("week", start === currentWeek ? null : start);

  const days = buildWeek(items, week, timezone, coverage);
  const inWeek = days.flatMap((day) => day.items);
  const earlier = week === currentWeek ? earlierThan(items, week, timezone) : [];
  const weekEnd = shiftDay(week, 6);
  const nextLater = items.find((item) => {
    const day = itemDay(item, timezone);
    return day !== null && day > weekEnd;
  });
  const posts = inWeek.filter((item) => item.content_type === "feed_image").length;
  const stories = inWeek.length - posts;

  return (
    <section
      aria-labelledby={headingId}
      data-testid="agenda-view"
      className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border bg-surface p-3 sm:p-5"
    >
      {/* Toolbar: where we are in time, and how to look at it. */}
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          {layout === "week" ? (
            <div className="flex items-center gap-1" role="group" aria-label={t("content.agenda.weekNav")}>
              <IconButton
                label={t("content.agenda.prevWeek")}
                disabled={week <= currentWeek}
                onClick={() => goWeek(shiftDay(week, -7))}
                testId="agenda-prev"
              >
                <ChevronLeftIcon />
              </IconButton>
              <Button
                variant="secondary"
                onClick={() => goWeek(currentWeek)}
                disabled={week === currentWeek}
                className="min-h-10 rounded-xl px-3 text-metadata"
              >
                {t("content.agenda.thisWeek")}
              </Button>
              <IconButton
                label={t("content.agenda.nextWeek")}
                disabled={week >= lastWeek}
                onClick={() => goWeek(shiftDay(week, 7))}
                testId="agenda-next"
              >
                <ChevronRightIcon />
              </IconButton>
            </div>
          ) : null}
          <div className="min-w-0">
            <h2 id={headingId} className="font-heading text-base leading-snug font-semibold tracking-tight text-primary first-letter:uppercase">
              {layout === "week" ? weekRangeLabel(week, i18n.language) : t("content.agenda.upcoming")}
            </h2>
            <p className="flex flex-wrap items-center gap-x-1.5 text-xs leading-5 text-secondary">
              {layout === "week" && scheduled.isSuccess ? (
                <>
                  <span data-testid="agenda-week-summary">{t("content.agenda.weekSummary", { posts, stories })}</span>
                  <span aria-hidden="true">·</span>
                </>
              ) : null}
              <span>{t("content.agendaNotice")}</span>
              <span aria-hidden="true">·</span>
              <span className="inline-flex items-center gap-1">
                <ClockIcon aria-hidden="true" />
                {timezoneLabel(timezone, t)}
              </span>
            </p>
          </div>
        </div>
        <div role="group" aria-label={t("content.agenda.layoutLabel")} className="inline-flex rounded-xl border border-border bg-surface-subtle/70 p-1">
          {(["week", "list"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={layout === option}
              onClick={() => setParam("layout", option === "week" ? null : option)}
              className={`min-h-11 rounded-lg px-3 text-metadata font-semibold transition-colors md:min-h-9 ${FOCUS} ${
                layout === option ? "bg-surface text-primary shadow-xs ring-1 ring-border" : "text-secondary hover:text-primary"
              }`}
            >
              {t(`content.agenda.${option}`)}
            </button>
          ))}
        </div>
      </div>

      {scheduled.isError ? <ErrorMessage error={scheduled.error} /> : null}
      {scheduled.isPending ? <AgendaSkeleton label={t("common.loading")} /> : null}

      {scheduled.isSuccess ? (
        <>
          {items.length === 0 ? <NothingScheduled draftCount={draftCount} onWrite={onWrite} /> : null}

          {layout === "week" ? (
            <>
              {earlier.length > 0 ? (
                <section aria-labelledby={`${headingId}-earlier`} className="flex flex-col gap-2 rounded-xl bg-info-subtle/70 p-3">
                  <h3 id={`${headingId}-earlier`} className="text-xs font-bold tracking-wider text-info uppercase">
                    {t("content.agenda.earlier")}
                  </h3>
                  <ul className="flex flex-col gap-1.5">
                    {earlier.map((item) => (
                      <li key={item.id}>
                        <AgendaRow item={item} withDay />
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {items.length > 0 && inWeek.length === 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface-subtle/70 px-4 py-3">
                  <p className="text-body text-secondary">{t("content.agenda.weekEmpty")}</p>
                  {nextLater?.scheduled_at ? (
                    <Button variant="secondary" className="min-h-10" onClick={() => goWeek(weekStartOf(itemDay(nextLater, timezone)!))}>
                      {t("content.agenda.jumpTo", {
                        when: friendlyMoment(nextLater.scheduled_at, timezone, i18n.language, t, { withTime: false }),
                      })}
                      <ChevronRightIcon />
                    </Button>
                  ) : null}
                </div>
              ) : null}

              <ol data-testid="agenda-week" className="grid gap-2 lg:grid-cols-7">
                {days.map((day) => (
                  <WeekDay key={day.day} day={day} />
                ))}
              </ol>
            </>
          ) : (
            <AgendaList items={items} />
          )}

          {coverage.capped ? (
            <p className="text-xs text-secondary">
              {t("content.agenda.capped", {
                count: LIST_LIMIT,
                day: coverage.lastDay
                  ? new Date(`${coverage.lastDay}T12:00:00Z`).toLocaleDateString(i18n.language, { day: "numeric", month: "long", timeZone: "UTC" })
                  : "",
              })}
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

/**
 * One day of the week. Phones and tablets read it as a row (date, then that day's items); from
 * 1024 px the seven days stand side by side as columns. It is one element either way.
 */
function WeekDay({ day }: { day: AgendaDay }) {
  const { t, i18n } = useTranslation();
  const date = new Date(`${day.day}T12:00:00Z`);
  const weekday = date.toLocaleDateString(i18n.language, { weekday: "short", timeZone: "UTC" });
  const number = date.toLocaleDateString(i18n.language, { day: "numeric", timeZone: "UTC" });
  const full = date.toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  const headingId = `agenda-day-${day.day}`;

  return (
    <li
      aria-labelledby={headingId}
      aria-current={day.isToday ? "date" : undefined}
      data-testid={`agenda-day-${day.day}`}
      className={`flex min-w-0 gap-3 rounded-xl p-2.5 lg:min-h-60 lg:flex-col lg:gap-2 lg:p-2 ${
        day.isToday ? "bg-assistant ring-1 ring-action/20" : day.notLoaded ? "border border-dashed border-border bg-transparent" : "bg-surface-subtle/70"
      }`}
    >
      <h3 id={headingId} className="sr-only">
        {day.isToday ? `${t("content.when.today")}, ` : ""}
        {full}
      </h3>
      <div
        aria-hidden="true"
        className={`flex w-11 shrink-0 flex-col items-center gap-0.5 pt-0.5 lg:w-auto lg:flex-row lg:items-center lg:justify-between lg:px-1 ${
          day.isPast ? "opacity-60" : ""
        }`}
      >
        <span className={`text-[0.6875rem] font-semibold tracking-wide uppercase ${day.isToday ? "text-action" : "text-secondary"}`}>
          {weekday}
        </span>
        <span
          className={`flex size-8 items-center justify-center rounded-full font-heading text-base font-bold tabular-nums ${
            day.isToday ? "bg-action text-on-action" : "text-primary"
          }`}
        >
          {number}
        </span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-center lg:justify-start">
        {day.items.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {day.items.map((item) => (
              <li key={item.id}>
                <BoardEntry item={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p className={`py-2 text-xs lg:pt-8 lg:text-center ${day.notLoaded ? "text-secondary" : "text-secondary/70"}`}>
            {day.notLoaded ? t("content.agenda.notLoaded") : day.isPast ? t("content.agenda.past") : t("content.agenda.free")}
          </p>
        )}
      </div>
    </li>
  );
}

/** A scheduled item on the week board: a row on narrow screens, a small card in a column. */
function BoardEntry({ item }: { item: ContentItem }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);
  const settled = item.status === "scheduled";
  return (
    <Link
      to={`/w/${workspace.id}/content/${item.id}`}
      data-testid="agenda-entry"
      className={`group flex min-w-0 gap-2.5 rounded-lg bg-surface p-1.5 ring-1 ring-border transition-colors hover:ring-action/40 lg:flex-col lg:gap-1.5 ${FOCUS}`}
    >
      <div className="relative w-12 shrink-0 lg:w-full">
        <ContentMedia item={item} compact className="aspect-[4/5] w-full rounded-md lg:aspect-[16/11]" />
        <span className="absolute top-1 left-1 hidden lg:block">
          <TypePill type={item.content_type} className="px-1.5" />
        </span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1 lg:px-0.5 lg:pb-0.5">
        <p className="flex items-center gap-1.5 text-xs">
          <span className="font-semibold text-primary tabular-nums">
            {item.scheduled_at ? timeOfDay(item.scheduled_at, workspace.timezone, i18n.language) : t("content.agenda.noTime")}
          </span>
          <span className="text-secondary lg:hidden">· {t(`content.type.${item.content_type}`)}</span>
        </p>
        <p className="line-clamp-2 text-metadata leading-snug font-semibold break-words text-primary transition-colors group-hover:text-action">
          {item.title || t("content.card.untitled")}
        </p>
        <span className="flex flex-wrap gap-1">
          {settled ? (
            item.is_simulated ? <SimulatedBadge compact /> : null
          ) : (
            <StatusBadge
              compact
              status={badge.status}
              params={badge.params}
              simulated={item.is_simulated}
              className="max-w-full [&>span:first-child]:max-w-full [&>span:first-child]:rounded-md"
            />
          )}
        </span>
      </div>
    </Link>
  );
}

/** Every scheduled item, grouped by day: the whole plan at once. */
function AgendaList({ items }: { items: ContentItem[] }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const today = todayIn(workspace.timezone);
  const groups = groupByDay(items, workspace.timezone);
  if (groups.length === 0) return null;
  return (
    <ol data-testid="agenda-list" className="flex flex-col gap-5">
      {groups.map((group) => {
        const date = group.day ? new Date(`${group.day}T12:00:00Z`) : null;
        const relative =
          group.day === today ? t("content.when.today") : group.day === shiftDay(today, 1) ? t("content.when.tomorrow") : null;
        const headingId = `agenda-list-${group.day ?? "none"}`;
        return (
          <li key={group.day ?? "none"} aria-labelledby={headingId} className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <h3 id={headingId} className="flex min-w-0 items-center gap-2.5 text-body font-semibold text-primary">
                <span
                  aria-hidden="true"
                  className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base ${
                    group.day === today ? "bg-action text-on-action" : "bg-surface-subtle text-action"
                  }`}
                >
                  <CalendarIcon />
                </span>
                <span className="truncate first-letter:uppercase">
                  {relative ? <span className="text-action">{relative} · </span> : null}
                  {date
                    ? date.toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
                    : t("content.agenda.noTime")}
                </span>
              </h3>
              <span className="shrink-0 rounded-full bg-surface-subtle px-2.5 py-0.5 text-xs font-semibold text-secondary tabular-nums">
                {group.items.length}
              </span>
            </div>
            <ul className="flex flex-col gap-1.5">
              {group.items.map((item) => (
                <li key={item.id}>
                  <AgendaRow item={item} />
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}

/** A scheduled item as one row: time, image, title and text, and the canonical status. */
function AgendaRow({ item, withDay = false }: { item: ContentItem; withDay?: boolean }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);
  const text = textPreview(item);
  const time = item.scheduled_at
    ? withDay
      ? friendlyMoment(item.scheduled_at, workspace.timezone, i18n.language, t)
      : timeOfDay(item.scheduled_at, workspace.timezone, i18n.language)
    : t("content.agenda.noTime");
  return (
    <Link
      to={`/w/${workspace.id}/content/${item.id}`}
      data-testid="agenda-entry"
      className={`group flex min-w-0 items-center gap-3 rounded-xl bg-surface px-2.5 py-2 ring-1 ring-border transition-colors hover:ring-action/40 sm:px-3 ${FOCUS}`}
    >
      <span className={`shrink-0 font-heading text-body font-semibold text-primary tabular-nums ${withDay ? "w-24 text-xs sm:w-28" : "w-12"}`}>
        {time}
      </span>
      <ContentMedia item={item} compact className="aspect-[4/5] w-10 shrink-0 rounded-md" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="truncate text-body leading-snug font-semibold text-primary transition-colors group-hover:text-action">
          {item.title || t("content.card.untitled")}
        </p>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <TypePill type={item.content_type} />
          <StatusBadge compact status={badge.status} params={badge.params} simulated={item.is_simulated} />
          {text ? <span className="hidden min-w-0 flex-1 truncate text-xs text-secondary md:block">{text}</span> : null}
        </div>
      </div>
      <ChevronRightIcon aria-hidden="true" className="shrink-0 text-lg text-secondary/50 transition-transform group-hover:translate-x-0.5 group-hover:text-action" />
    </Link>
  );
}

/** Nothing is scheduled at all: say so once, with the step that leads here. */
function NothingScheduled({ draftCount, onWrite }: { draftCount: number; onWrite: () => void }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  return (
    <div data-testid="agenda-empty" className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl bg-assistant px-4 py-3.5">
      <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface text-lg text-action">
        <CalendarIcon />
      </span>
      <div className="min-w-0 flex-1 basis-56">
        <p className="text-body font-semibold text-primary">{t("content.agendaEmpty")}</p>
        <p className="text-xs text-secondary">{t("content.agenda.emptyHint")}</p>
      </div>
      {draftCount > 0 ? (
        <Link
          to={`/w/${workspace.id}/content?tab=drafts`}
          className={`inline-flex min-h-11 items-center gap-2 rounded-control border border-border bg-surface px-4 text-body font-medium text-primary transition-colors hover:bg-surface-subtle ${FOCUS}`}
        >
          <PencilIcon aria-hidden="true" className="text-base" />
          {t("content.agenda.reviewDrafts", { count: draftCount })}
        </Link>
      ) : (
        <Button onClick={onWrite}>
          <SparkIcon className="text-base" />
          {t("content.emptyAction.write")}
        </Button>
      )}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
  testId,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className={`flex size-11 items-center justify-center rounded-xl border border-border bg-surface text-lg text-primary transition-colors enabled:hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40 ${FOCUS}`}
    >
      {children}
    </button>
  );
}

function AgendaSkeleton({ label }: { label: string }) {
  return (
    <div role="status" className="grid gap-2 lg:grid-cols-7">
      <span className="sr-only">{label}</span>
      {Array.from({ length: 7 }, (_, index) => (
        <div key={index} aria-hidden="true" className="h-16 rounded-xl bg-surface-subtle motion-safe:animate-pulse lg:h-60" />
      ))}
    </div>
  );
}
