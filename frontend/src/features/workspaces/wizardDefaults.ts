import type { WorkspaceCreateBody } from "@/api/types";

export type Market = WorkspaceCreateBody["market"];
export type MarketDefaults = Pick<WorkspaceCreateBody, "default_locale" | "timezone" | "currency">;

/** Defaults follow the market, never the UI language (ADR-016): Türkiye vs everywhere else. */
export function defaultsForMarket(market: Market, browserTimezone: string): MarketDefaults {
  if (market === "tr") {
    return { default_locale: "tr", timezone: "Europe/Istanbul", currency: "TRY" };
  }
  return { default_locale: "en", timezone: browserTimezone || "UTC", currency: "EUR" };
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return "UTC";
  }
}

export function timezoneOptions(selected: string): string[] {
  const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
  const all = supported ? supported("timeZone") : [];
  return all.includes(selected) ? all : [selected, ...all];
}

export const CURRENCIES = ["TRY", "EUR", "USD", "GBP"] as const;
