import type { TFunction } from "i18next";
import type { ContentItem } from "@/api/types";

/** Codes from which a publish is retried by itself (observability §4: retryable). */
export const AUTO_RETRY = new Set(["PROVIDER_UNAVAILABLE", "PROVIDER_RATE_LIMITED", "PUBLISH_QUOTA_EXHAUSTED"]);

/** Why the item is in trouble, or null: a failure or retry code, or an unknown outcome being checked. */
export function failureCode(item: Pick<ContentItem, "status" | "operation" | "last_error_code">): string | null {
  if (item.status === "publishing") return item.operation?.status === "outcome_unknown" ? "OUTCOME_UNKNOWN" : null;
  if (item.status === "failed" || item.status === "retry_scheduled") {
    return item.last_error_code ?? item.operation?.last_error_code ?? "UNKNOWN";
  }
  return null;
}

/** What happened and what to do, from the error catalog; a code without text reads as a generic failure. */
export function failureText(code: string, t: TFunction): { what: string; next: string } {
  const what = t(`errors.${code}.what`, { defaultValue: "" });
  if (what === "" || code === "UNKNOWN") {
    return { what: t("content.failure.unknown.what"), next: t("content.failure.unknown.next") };
  }
  return { what, next: t(`errors.${code}.next`) };
}

