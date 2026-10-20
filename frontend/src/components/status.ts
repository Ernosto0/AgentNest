/**
 * Display states shared by every screen (user-journeys.md §1). The labels live in the
 * catalogs under `status.<key>`; `StatusBadge` is the only component that renders them.
 */
export const STATUS_KEYS = [
  "draft",
  "pending_approval",
  "needs_human",
  "scheduled",
  "on_hold",
  "sending",
  "publishing",
  "checking",
  "sent",
  "published",
  "failed",
  "expired",
  "retry_scheduled",
  "rejected",
  "cancelled",
] as const;

export type StatusKey = (typeof STATUS_KEYS)[number];
