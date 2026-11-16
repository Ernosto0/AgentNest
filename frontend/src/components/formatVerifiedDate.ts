/** "3 Nov" in the UI language and the workspace time zone (INV-19); the year only when it is not this year. */
export function formatVerifiedDate(value: string, language: string, timeZone?: string, now = new Date()): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const zone = timeZone ? { timeZone } : {};
  const sameYear = date.toLocaleDateString("en-CA", { year: "numeric", ...zone }).slice(0, 4) === now.toLocaleDateString("en-CA", { year: "numeric", ...zone }).slice(0, 4);
  return date.toLocaleDateString(language, { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }), ...zone });
}
