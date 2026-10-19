import type { TFunction } from "i18next";

/**
 * The backend answers commands with a stable `message_key` plus formatted `params` (never a
 * sentence). These are the keys it can use; `commands.test.ts` pins that each one has text in
 * both languages, because `t()` is called with a run-time key here.
 */
export const RESULT_MESSAGE_KEYS = [
  "fact_value",
  "fact_not_usable",
  "fact_unchanged",
  "fact_updated",
  "fact_proposed",
  "brand_voice_updated",
  "brand_voice_proposed",
  "fact_changed_meanwhile",
  "pending_approvals",
  "activity_basic",
  "forbidden",
  "value_unreadable",
  "brand_voice_missing",
  "failed",
] as const;

export const UNSUPPORTED_REASONS = [
  "publish",
  "send_message",
  "approve",
  "manage_account",
  "settings",
  "members",
  "other",
] as const;

export const SUGGESTION_KEYS = ["update_price", "ask_price", "activity"] as const;
export const LINK_TARGETS = [
  "knowledge",
  "approvals",
  "content",
  "inbox",
  "integrations",
  "automation",
  "members",
] as const;
export const PERIODS = ["today", "yesterday", "last_7_days"] as const;
export const CLARIFY_QUESTIONS = ["which_fact", "which_fact_value", "which_value"] as const;

/** `command.fact_updated` -> `fact_updated`. */
export function messageSuffix(messageKey: string): string {
  return messageKey.replace(/^command\./, "");
}

export interface ResultLink {
  target: string;
  category?: string;
  key?: string;
}

/** Where a result link leads (structured by the API, so it holds no frontend route). */
export function linkPath(workspaceId: string, link: ResultLink): string {
  const base = `/w/${workspaceId}`;
  switch (link.target) {
    case "knowledge":
      return link.category ? `${base}/more/knowledge/${link.category}` : `${base}/more/knowledge`;
    case "approvals":
      return `${base}/approvals`;
    case "content":
      return `${base}/content`;
    case "inbox":
      return `${base}/inbox`;
    default:
      return `${base}/more`;
  }
}

/** The sentence for a command result, in the user's language. */
export function describeResult(
  t: TFunction,
  messageKey: string,
  params: Record<string, unknown>,
): string {
  const suffix = messageSuffix(messageKey);
  const known = (RESULT_MESSAGE_KEYS as readonly string[]).includes(suffix);
  const values: Record<string, unknown> = { ...params };
  if (suffix === "fact_not_usable") {
    values.stateLabel = t(`knowledge.state.${String(params.state)}`, { defaultValue: String(params.state) });
  }
  if (suffix === "activity_basic") {
    values.periodLabel = t(`command.period.${String(params.period)}`, {
      defaultValue: String(params.period),
    });
  }
  if (suffix === "pending_approvals" && Number(params.count) === 0) {
    return t("command.msg.pending_none");
  }
  return t(`command.msg.${known ? suffix : "failed"}`, values) as string;
}
