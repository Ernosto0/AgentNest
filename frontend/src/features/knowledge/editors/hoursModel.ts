import type { FactValue } from "./fields";
import { asString } from "./util";

export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Day = (typeof DAYS)[number];
export type Range = [string, string];

export interface Row {
  days: Day[];
  ranges: Range[];
}
export interface Exception {
  date: string;
  closed: boolean;
  ranges: Range[];
}

function toRanges(raw: unknown): Range[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((pair): pair is [unknown, unknown] => Array.isArray(pair) && pair.length === 2)
    .map(([a, b]) => [asString(a), asString(b)]);
}

/** Group the days that share the same hours into one row (closed days belong to no row). */
export function rowsFromValue(value: FactValue | null): Row[] {
  const groups = new Map<string, Row>();
  for (const day of DAYS) {
    const ranges = toRanges(value?.[day]);
    if (ranges.length === 0) continue;
    const key = JSON.stringify(ranges);
    const row = groups.get(key) ?? { days: [], ranges };
    row.days.push(day);
    groups.set(key, row);
  }
  return [...groups.values()];
}

export function exceptionsFromValue(value: FactValue | null): Exception[] {
  const raw = value?.exceptions;
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => {
    const record = (item ?? {}) as Record<string, unknown>;
    return {
      date: asString(record.date),
      closed: record.closed !== false,
      ranges: toRanges(record.ranges),
    };
  });
}

const validRanges = (ranges: Range[]) =>
  ranges.every(([open, close]) => open !== "" && close !== "" && open < close);

/** Canonical value, or null while a range or date is incomplete. Overlaps are left to the server. */
export function buildHours(rows: Row[], exceptions: Exception[]): FactValue | null {
  if (rows.some((row) => !validRanges(row.ranges))) return null;
  if (
    exceptions.some((e) => !e.date || (!e.closed && (e.ranges.length === 0 || !validRanges(e.ranges))))
  ) {
    return null;
  }
  const out: FactValue = {};
  for (const day of DAYS) out[day] = [];
  for (const row of rows) for (const day of row.days) out[day] = row.ranges;
  out.exceptions = exceptions.map((e) => ({
    date: e.date,
    closed: e.closed,
    ranges: e.closed ? [] : e.ranges,
  }));
  return out;
}
