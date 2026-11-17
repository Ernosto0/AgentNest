import { shiftDay } from "./dates";

/** The Monday of the week that contains `day` (calendar arithmetic only, `YYYY-MM-DD`). */
export function mondayOf(day: string): string {
  const weekday = new Date(`${day}T00:00:00Z`).getUTCDay(); // 0 is Sunday
  return shiftDay(day, -((weekday + 6) % 7));
}

/** A week for people: "9 Mart – 15 Mart 2026". */
export function weekLabel(monday: string, language: string): string {
  const format = (day: string, withYear: boolean) =>
    new Date(`${day}T12:00:00Z`).toLocaleDateString(language, {
      day: "numeric",
      month: "long",
      ...(withYear ? { year: "numeric" } : {}),
      timeZone: "UTC",
    });
  return `${format(monday, false)} – ${format(shiftDay(monday, 6), true)}`;
}
