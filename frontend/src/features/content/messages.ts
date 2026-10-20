import type { TFunction } from "i18next";
import type { ContentCheckItem, ContentIssue } from "@/api/types";
import { timezoneCity } from "./schedule";

/** Every submit item code of plan.md G17 (observability §4.2); `messages.test` pins a text for each. */
export const SUBMIT_ITEM_CODES = [
  "CONTENT_MEDIA_REQUIRED",
  "MEDIA_NOT_READY",
  "CAPTION_REQUIRED",
  "CAPTION_TOO_LONG",
  "CAPTION_NOT_ALLOWED",
  "ASPECT_RATIO_OUT_OF_RANGE",
  "CLAIM_VALIDATION_FAILED",
  "SCHEDULE_IN_PAST",
  "SCHEDULE_TOO_FAR",
  "SCHEDULE_TIME_NONEXISTENT",
  "SCHEDULE_TOO_SOON_FOR_APPROVAL",
  "ACCOUNT_NOT_CONNECTED",
  "CAPABILITY_MISSING",
  "PUBLISH_QUOTA_FORECAST_EXCEEDED",
  "STORY_ASPECT_NOT_9_16",
  "OVERLAY_TOO_LONG",
] as const;

/** The item codes that are about the time, shown next to the date and time fields. */
export const SCHEDULE_ITEM_CODES: readonly string[] = [
  "SCHEDULE_IN_PAST",
  "SCHEDULE_TOO_FAR",
  "SCHEDULE_TIME_NONEXISTENT",
  "SCHEDULE_TOO_SOON_FOR_APPROVAL",
  "PUBLISH_QUOTA_FORECAST_EXCEEDED",
];

/** Capabilities an account can hold (plan.md G4); an unknown one is shown as its own name. */
export const CAPABILITY_KEYS = ["messaging", "publish_feed_image", "publish_story_image"] as const;

export function capabilityLabel(capability: string, t: TFunction): string {
  return (CAPABILITY_KEYS as readonly string[]).includes(capability)
    ? t(`content.capability.${capability}`)
    : capability;
}

/** "İstanbul saati" / "Istanbul time" for a zone id such as "Europe/Istanbul". */
export function timezoneLabel(timezone: string, t: TFunction): string {
  const city = timezoneCity(timezone);
  return t("content.schedule.timezoneLabel", {
    city: t(`content.schedule.city.${city}`, { defaultValue: city }),
  });
}

/** Plain-language text for a submit rule (plan.md G17): our catalog first, then the server's own message. */
export function checkMessage(item: Pick<ContentCheckItem, "code" | "params" | "message">, t: TFunction): string {
  const params: Record<string, unknown> = { ...item.params };
  if (typeof params.timezone === "string") params.timezoneLabel = timezoneLabel(params.timezone, t);
  return t(`content.editor.checks.${item.code}`, {
    ...params,
    defaultValue: item.message ?? item.code,
  });
}

/** The sentence for a claim issue that blocks (a grounded one is shown as a fact chip instead). */
export function blockingIssueMessage(issue: ContentIssue, t: TFunction): string {
  return t(`content.editor.issues.${issue.code}`, {
    text: issue.text,
    defaultValue: t("content.editor.issues.blocking", { text: issue.text }),
  });
}
