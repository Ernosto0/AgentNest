/** Friendly, locale-aware labels for workspace identifiers (time zones, currencies). */

/** The current UTC offset of a time zone, e.g. "GMT+03:00", or null if the zone is unknown. */
export function timezoneOffset(timezone: string, locale: string, at: Date = new Date()): string | null {
  try {
    const part = new Intl.DateTimeFormat(locale, { timeZone: timezone, timeZoneName: "longOffset" })
      .formatToParts(at)
      .find((p) => p.type === "timeZoneName");
    return part?.value ?? null;
  } catch {
    return null;
  }
}

/** "Europe/Istanbul" -> "Istanbul (GMT+03:00)"; "America/Argentina/Buenos_Aires" -> "Buenos Aires (…)". */
export function timezoneLabel(timezone: string, locale: string, at?: Date): string {
  const city = (timezone.split("/").pop() ?? timezone).replaceAll("_", " ");
  const offset = timezoneOffset(timezone, locale, at);
  return offset ? `${city} (${offset})` : city;
}

/** "TRY" -> "Turkish lira (TRY)" in the UI language, falling back to the bare code. */
export function currencyLabel(code: string, locale: string): string {
  try {
    const name = new Intl.DisplayNames([locale], { type: "currency" }).of(code);
    return name && name !== code ? `${name} (${code})` : code;
  } catch {
    return code;
  }
}
