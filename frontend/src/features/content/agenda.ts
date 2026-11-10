import type { TFunction } from "i18next";
import type { ContentItem } from "@/api/types";
import { shiftDay, todayIn } from "@/features/reports/dates";

/**
 * Agenda arithmetic on the workspace clock (INV-19). Days are `YYYY-MM-DD` strings; weeks start
 * on Monday. Only scheduled-tab items are placed, and only where the fetched page covers the day.
 */

const LOCAL_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Monday of the week that holds `day`. */
export function weekStartOf(day: string): string {
  const weekday = new Date(`${day}T12:00:00Z`).getUTCDay(); // 0 = Sunday
  return shiftDay(day, -((weekday + 6) % 7));
}

/** A `week` address parameter, normalised to its Monday, or null when it is not a date. */
export function parseWeekParam(value: string | null): string | null {
  if (value === null || !LOCAL_DAY.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) return null;
  return weekStartOf(value);
}

/** The local day an item is placed on, or null when it has no time to place it by. */
export function itemDay(item: Pick<ContentItem, "scheduled_at">, timezone: string): string | null {
  return item.scheduled_at ? todayIn(timezone, new Date(item.scheduled_at)) : null;
}

export interface AgendaDay {
  day: string;
  items: ContentItem[];
  isToday: boolean;
  isPast: boolean;
  /** The fetched page ended before this day: an empty day here is unknown, not empty. */
  notLoaded: boolean;
}

export interface AgendaCoverage {
  /** The list was a full page, so later items may exist. */
  capped: boolean;
  /** With a full page: the last day that was fetched. Days after it are not known. */
  lastDay: string | null;
}

/** Items ordered by their time; an item without one sorts last. */
export function byScheduledTime(items: readonly ContentItem[]): ContentItem[] {
  return [...items].sort((a, b) => {
    if (a.scheduled_at === b.scheduled_at) return a.id.localeCompare(b.id);
    if (a.scheduled_at === null) return 1;
    if (b.scheduled_at === null) return -1;
    return a.scheduled_at.localeCompare(b.scheduled_at);
  });
}

export function coverageOf(items: readonly ContentItem[], limit: number, timezone: string): AgendaCoverage {
  if (items.length < limit) return { capped: false, lastDay: null };
  const days = items.map((item) => itemDay(item, timezone)).filter((day): day is string => day !== null);
  return { capped: true, lastDay: days.sort().at(-1) ?? null };
}

/** Seven days from `weekStart`, each with its items in time order. */
export function buildWeek(
  items: readonly ContentItem[],
  weekStart: string,
  timezone: string,
  coverage: AgendaCoverage,
  now: Date = new Date(),
): AgendaDay[] {
  const today = todayIn(timezone, now);
  const sorted = byScheduledTime(items);
  return Array.from({ length: 7 }, (_, index) => {
    const day = shiftDay(weekStart, index);
    return {
      day,
      items: sorted.filter((item) => itemDay(item, timezone) === day),
      isToday: day === today,
      isPast: day < today,
      notLoaded: coverage.capped && coverage.lastDay !== null && day > coverage.lastDay,
    };
  });
}

/**
 * Items the week board cannot place: scheduled before the current week (a late or retrying
 * attempt) or with no time at all. They are listed above the current week so nothing disappears.
 */
export function earlierThan(items: readonly ContentItem[], weekStart: string, timezone: string): ContentItem[] {
  return byScheduledTime(items).filter((item) => {
    const day = itemDay(item, timezone);
    return day === null || day < weekStart;
  });
}

/** Every item grouped by its local day, earliest first (the list layout). Items with no time come last. */
export function groupByDay(items: readonly ContentItem[], timezone: string): { day: string | null; items: ContentItem[] }[] {
  const groups = new Map<string | null, ContentItem[]>();
  for (const item of byScheduledTime(items)) {
    const day = itemDay(item, timezone);
    groups.set(day, [...(groups.get(day) ?? []), item]);
  }
  return [...groups.entries()].map(([day, grouped]) => ({ day, items: grouped }));
}

/** "10–16 Kasım 2026" / "28 Eki – 3 Kas 2026": the visible label of a week. */
export function weekRangeLabel(weekStart: string, language: string): string {
  const start = new Date(`${weekStart}T12:00:00Z`);
  const end = new Date(`${shiftDay(weekStart, 6)}T12:00:00Z`);
  try {
    return new Intl.DateTimeFormat(language, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).formatRange(start, end);
  } catch {
    const format = (date: Date) => date.toLocaleDateString(language, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    return `${format(start)} – ${format(end)}`;
  }
}

/**
 * A moment for people, on the workspace clock: "Bugün · 19:00", "Yarın · 09:30", "12 Kas · 19:00"
 * (the year only when it is not this year). `withTime: false` leaves the time out.
 */
export function friendlyMoment(
  at: string,
  timezone: string,
  language: string,
  t: TFunction,
  { withTime = true }: { withTime?: boolean } = {},
  now: Date = new Date(),
): string {
  const date = new Date(at);
  const day = todayIn(timezone, date);
  const today = todayIn(timezone, now);
  let dayText: string;
  if (day === today) dayText = t("content.when.today");
  else if (day === shiftDay(today, 1)) dayText = t("content.when.tomorrow");
  else if (day === shiftDay(today, -1)) dayText = t("content.when.yesterday");
  else {
    dayText = date.toLocaleDateString(language, {
      day: "numeric",
      month: "short",
      ...(day.slice(0, 4) === today.slice(0, 4) ? {} : { year: "numeric" }),
      timeZone: timezone,
    });
  }
  if (!withTime) return dayText;
  const time = date.toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit", timeZone: timezone });
  return `${dayText} · ${time}`;
}

/** The time of day only: "19:00". */
export function timeOfDay(at: string, timezone: string, language: string): string {
  return new Date(at).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit", timeZone: timezone });
}
