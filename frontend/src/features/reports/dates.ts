import { wallClock } from "@/features/content/schedule";

const LOCAL_DAY = /^\d{4}-\d{2}-\d{2}$/;

export function isLocalDay(value: unknown): value is string {
  return typeof value === "string" && LOCAL_DAY.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Today's date on the workspace clock (INV-19), as `YYYY-MM-DD`. */
export function todayIn(timezone: string, now: Date = new Date()): string {
  const wall = wallClock(now, timezone);
  return `${wall.year}-${pad(wall.month)}-${pad(wall.day)}`;
}

/** The day before or after `day` (calendar arithmetic only, so no DST can get in the way). */
export function shiftDay(day: string, by: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + by);
  return date.toISOString().slice(0, 10);
}

/** A local day for people: "15 Ekim 2026 Perşembe". */
export function dayLabel(day: string, language: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString(language, { dateStyle: "full", timeZone: "UTC" });
}
