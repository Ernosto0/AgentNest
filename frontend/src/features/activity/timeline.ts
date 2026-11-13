import type { ActivityEntry, ActivityLevel } from "@/api/types";
import { todayIn } from "@/features/reports/dates";

/**
 * Activity timeline shaping (presentation only; no entry is dropped, merged away or altered).
 *
 * Entries arrive newest first, page by page. They are split into local days on the workspace
 * clock. Inside a day, entries that share the server's `collapse_key` (MIN_GROUP or more) gather
 * into one visual group placed where its newest entry would be, showing the time range it spans;
 * every other entry keeps its chronological place, and the group opens to its entries in order.
 * The key is the server's statement that the entries describe the same kind of thing (one alert
 * condition, the same action on the same record); the client never guesses from titles. The
 * transform runs over every loaded entry, so a day that continues on the next page simply gains
 * entries when that page arrives; until then its counts are marked open-ended.
 */

/** Fewer entries than this stay as individual rows: grouping two rows saves nothing. */
export const MIN_GROUP = 3;

export type TimelineItem =
  | { kind: "entry"; entry: ActivityEntry }
  | {
      kind: "group";
      key: string;
      /** Newest first, exactly as received. */
      entries: ActivityEntry[];
      /** The most serious level among the entries. */
      level: ActivityLevel;
      /** True when the day may continue on a page that is not loaded yet. */
      openEnded: boolean;
    };

export interface DaySection {
  /** Local date on the workspace clock, YYYY-MM-DD. */
  day: string;
  items: TimelineItem[];
  /** Entries in this day section (loaded so far). */
  count: number;
  /** True when this is the last loaded day and more pages exist. */
  openEnded: boolean;
}

const SEVERITY: Record<ActivityLevel, number> = { failure: 3, warning: 2, success: 1, info: 0 };

export function worstLevel(entries: ActivityEntry[]): ActivityLevel {
  let worst: ActivityLevel = "info";
  for (const entry of entries) if (SEVERITY[entry.level] > SEVERITY[worst]) worst = entry.level;
  return worst;
}

export function buildTimeline(entries: ActivityEntry[], timezone: string, hasMore: boolean): DaySection[] {
  const days: { day: string; entries: ActivityEntry[] }[] = [];
  for (const entry of entries) {
    const day = todayIn(timezone, new Date(entry.occurred_at));
    const last = days.at(-1);
    if (last && last.day === day) last.entries.push(entry);
    else days.push({ day, entries: [entry] });
  }
  return days.map(({ day, entries: dayEntries }, index) => {
    const isLastDay = index === days.length - 1;
    const openEnded = isLastDay && hasMore;
    const byKey = new Map<string, ActivityEntry[]>();
    for (const entry of dayEntries) {
      const members = byKey.get(entry.collapse_key);
      if (members) members.push(entry);
      else byKey.set(entry.collapse_key, [entry]);
    }
    const items: TimelineItem[] = [];
    for (const entry of dayEntries) {
      const members = byKey.get(entry.collapse_key) ?? [entry];
      if (members.length < MIN_GROUP) {
        items.push({ kind: "entry", entry });
      } else if (members[0] === entry) {
        items.push({ kind: "group", key: `${entry.collapse_key}:${entry.id}`, entries: members, level: worstLevel(members), openEnded });
      }
    }
    return { day, items, count: dayEntries.length, openEnded };
  });
}
