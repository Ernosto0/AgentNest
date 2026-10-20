import type { TFunction } from "i18next";
import type { StatusKey } from "@/components/status";
import type { ContentItem, ContentStatus, ContentTab } from "@/api/types";

/** The content screen's tabs and the statuses each one lists (plan.md G15). `cancelled` is in none. */
export const CONTENT_TABS: readonly ContentTab[] = ["drafts", "scheduled", "published", "problems"];

export const TAB_STATUSES: Record<ContentTab, readonly ContentStatus[]> = {
  drafts: ["draft", "pending_approval"],
  scheduled: ["scheduled", "publishing", "retry_scheduled"],
  published: ["published"],
  problems: ["on_hold", "failed", "rejected"],
};

export function isContentTab(value: string | null): value is ContentTab {
  return value !== null && (CONTENT_TABS as readonly string[]).includes(value);
}

/** The tab an item is listed in, or null (cancelled items are only found by status). */
export function tabOf(status: ContentStatus): ContentTab | null {
  return CONTENT_TABS.find((tab) => TAB_STATUSES[tab].includes(status)) ?? null;
}

export interface ContentBadge {
  status: StatusKey;
  params?: { time: string };
}

/**
 * The single place where a content item's server state becomes a display state (INV-18).
 * Only a `published` item reads "published". An attempt whose outcome is not known reads
 * "checking" (never "publishing" or "published"), and a retry says when it will happen.
 */
export function contentBadge(
  item: Pick<ContentItem, "status" | "operation">,
  t: TFunction,
  language: string,
  timezone: string,
): ContentBadge {
  switch (item.status) {
    case "publishing":
      return { status: item.operation?.status === "outcome_unknown" ? "checking" : "publishing" };
    case "retry_scheduled": {
      const next = item.operation?.next_attempt_at ?? null;
      const time = next
        ? new Date(next).toLocaleTimeString(language, {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: timezone,
          })
        : t("content.status.soon");
      return { status: "retry_scheduled", params: { time } };
    }
    default:
      return { status: item.status };
  }
}

/** Statuses an owner can still edit. Editing a pending or scheduled item sends it back to draft (api-design §2.7). */
const EDITABLE: readonly ContentStatus[] = [
  "draft",
  "pending_approval",
  "scheduled",
  "on_hold",
  "rejected",
  "failed",
];

export function isEditable(status: ContentStatus): boolean {
  return EDITABLE.includes(status);
}

/** Editing voids the approval of these: the server returns them to draft. */
export function editVoidsApproval(status: ContentStatus): boolean {
  return status === "pending_approval" || status === "scheduled";
}
