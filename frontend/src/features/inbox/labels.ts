import type { Conversation } from "@/api/types";

/** The label of a customer: the handle if known, else a short stable number. */
export function customerLabel(
  conversation: Pick<Conversation, "customer_handle" | "customer_number">,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  return conversation.customer_handle ?? t("convo.customer", { number: conversation.customer_number });
}

/** Initials for an avatar; a numbered customer ("Müşteri #4821") keeps the last two digits. */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  if (/#\d+$/.test(trimmed)) return `#${trimmed.replace(/[^0-9]/g, "").slice(-2)}`;
  const parts = trimmed.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
  return trimmed.slice(0, 2).toUpperCase();
}

/** The calendar day of an instant in a time zone, as YYYY-MM-DD. */
export const dayKey = (date: Date, timeZone: string) => date.toLocaleDateString("en-CA", { timeZone });

/** Whole days between two calendar days in the workspace time zone (0 = same day). */
export function daysAgo(value: string, timeZone: string, now = new Date()): number {
  const then = Date.parse(dayKey(new Date(value), timeZone));
  const today = Date.parse(dayKey(now, timeZone));
  return Math.round((today - then) / 86_400_000);
}
