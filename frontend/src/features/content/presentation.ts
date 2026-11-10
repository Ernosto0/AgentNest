import type { TFunction } from "i18next";
import type { ContentItem, ContentTab } from "@/api/types";
import { failureCode, failureText } from "./failure";
import { tabOf } from "./status";

/** The words that would go out: the caption of a post, or the overlay lines of a story. */
export function textPreview(item: Pick<ContentItem, "content_type" | "caption" | "overlay_text_suggestions">): string {
  if (item.content_type === "story_image") {
    return item.overlay_text_suggestions.filter((line) => line.trim() !== "").join(" · ");
  }
  return item.caption?.trim() ?? "";
}

/** Why an item in Problems is there, in a sentence, or null for any other item. */
export function problemReason(item: ContentItem, t: TFunction): string | null {
  if (item.status === "on_hold") {
    return t(`content.hold.${item.hold_reason ?? "unknown"}.what`, { defaultValue: t("content.hold.unknown.what") });
  }
  if (item.status === "failed") return failureText(failureCode(item) ?? "UNKNOWN", t).what;
  if (item.status === "rejected") {
    return item.rejection_note ? t("content.card.rejectedNote", { note: item.rejection_note }) : null;
  }
  return null;
}

/** A tab's items as listed: the server filters by tab, and a defensive filter keeps a cancelled or foreign-tab item out. */
export function tabItems(data: ContentItem[] | undefined, tab: ContentTab): ContentItem[] | undefined {
  return data?.filter((item) => tabOf(item.status) === tab);
}
