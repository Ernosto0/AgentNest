/**
 * Local date and time <-> instants for the schedule picker (INV-19).
 *
 * The API takes the schedule as the wall-clock time the owner typed (`{local_date, local_time}`
 * in the workspace timezone) and converts it itself, so nothing here goes on the wire as an
 * instant. These helpers only let the form tell the owner early what the server would say about
 * the time (past, in a clock gap, too soon for an approval); the server stays authoritative.
 */

/** A post that waits for an approver must be at least this far ahead (SCHEDULE_TOO_SOON_FOR_APPROVAL). */
export const APPROVAL_LEAD_MINUTES = 15;
/** The server accepts a time up to a minute in the past (clock skew). */
export const PAST_GRACE_MINUTES = 1;

const MINUTE = 60_000;

interface Wall {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(timezone: string): Intl.DateTimeFormat {
  let known = formatters.get(timezone);
  if (!known) {
    known = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    formatters.set(timezone, known);
  }
  return known;
}

/** The wall clock in `timezone` at the instant `at` (to the minute). */
export function wallClock(at: Date, timezone: string): Wall {
  const parts = formatter(timezone).formatToParts(new Date(Math.floor(at.getTime() / MINUTE) * MINUTE));
  const read = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? "0");
  return { year: read("year"), month: read("month"), day: read("day"), hour: read("hour"), minute: read("minute") };
}

const wallAsUtc = (wall: Wall) => Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute);

/** Offset of `timezone` from UTC at an instant, in milliseconds. */
function offsetAt(instantMs: number, timezone: string): number {
  return wallAsUtc(wallClock(new Date(instantMs), timezone)) - Math.floor(instantMs / MINUTE) * MINUTE;
}

/**
 * The instant a local date ("2026-10-21") and time ("19:00") mean in `timezone`.
 * `null` when the input is malformed or the time does not exist (the hour skipped when clocks
 * go forward: the server answers SCHEDULE_TIME_NONEXISTENT). A time that exists twice (clocks go
 * back) is the earlier instant, like the server's.
 */
export function localToInstant(localDate: string, localTime: string, timezone: string): Date | null {
  const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  const time = /^(\d{2}):(\d{2})$/.exec(localTime);
  if (!date || !time) return null;
  const wall: Wall = {
    year: Number(date[1]),
    month: Number(date[2]),
    day: Number(date[3]),
    hour: Number(time[1]),
    minute: Number(time[2]),
  };
  const wanted = wallAsUtc(wall);
  // The offsets on both sides of any transition within a day of the wanted time.
  const offsets = new Set([offsetAt(wanted - 24 * 60 * MINUTE, timezone), offsetAt(wanted + 24 * 60 * MINUTE, timezone)]);
  const matches = [...offsets]
    .map((offset) => wanted - offset)
    .filter((candidate) => wallAsUtc(wallClock(new Date(candidate), timezone)) === wanted)
    .sort((a, b) => a - b);
  return matches.length > 0 ? new Date(matches[0]!) : null;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** `{date, time}` strings of an instant on the workspace clock, ready for the date and time inputs. */
export function toLocalFields(at: Date, timezone: string): { date: string; time: string } {
  const wall = wallClock(at, timezone);
  return { date: `${wall.year}-${pad(wall.month)}-${pad(wall.day)}`, time: `${pad(wall.hour)}:${pad(wall.minute)}` };
}

/** A sensible first suggestion: an hour from now, rounded up to five minutes, on the workspace clock. */
export function defaultSchedule(now: Date, timezone: string): { date: string; time: string } {
  const fiveMinutes = 5 * MINUTE;
  const target = new Date(Math.ceil((now.getTime() + 60 * MINUTE) / fiveMinutes) * fiveMinutes);
  return toLocalFields(target, timezone);
}

/** Mirrors what the server would say about a chosen time (before asking it). */
export type ScheduleProblem = "SCHEDULE_TIME_NONEXISTENT" | "SCHEDULE_IN_PAST" | "SCHEDULE_TOO_SOON_FOR_APPROVAL";

export function scheduleProblem(
  localDate: string,
  localTime: string,
  timezone: string,
  now: Date,
  waitsForApproval: boolean,
): ScheduleProblem | null {
  const instant = localToInstant(localDate, localTime, timezone);
  if (instant === null) {
    return /^\d{4}-\d{2}-\d{2}$/.test(localDate) && /^\d{2}:\d{2}$/.test(localTime) ? "SCHEDULE_TIME_NONEXISTENT" : null;
  }
  if (instant.getTime() < now.getTime() - PAST_GRACE_MINUTES * MINUTE) return "SCHEDULE_IN_PAST";
  if (waitsForApproval && instant.getTime() < now.getTime() + APPROVAL_LEAD_MINUTES * MINUTE) {
    return "SCHEDULE_TOO_SOON_FOR_APPROVAL";
  }
  return null;
}

/** "Europe/Istanbul" -> "Istanbul": the city part of the zone name, for "İstanbul saati". */
export function timezoneCity(timezone: string): string {
  const last = timezone.split("/").pop() ?? timezone;
  return last.replace(/_/g, " ");
}
