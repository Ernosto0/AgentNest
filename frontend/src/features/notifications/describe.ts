import type { AppNotification } from "@/api/types";

type Labelled = Record<string, string> | string | null | undefined;

function pick(value: Labelled, language: string): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") return value[language] ?? value.tr ?? value.en ?? "";
  return "";
}

/** The sentence for a notification, from its type and params (the API stores no prose). */
export function describeNotification(
  t: (key: string, options?: Record<string, unknown>) => string,
  notification: AppNotification,
  language: string,
): string {
  const params = notification.params as Record<string, unknown>;
  const summary = (params.summary ?? {}) as Record<string, unknown>;
  const type = notification.type.replace(/\./g, "_");
  const label = pick((params.label as Labelled) ?? (summary.label as Labelled), language);
  switch (notification.type) {
    case "approval.requested":
    case "approval.expired":
      return t(`notifications.type.${type}`, { label: label || pick(summary.label as Labelled, language) });
    case "knowledge.fact_changed":
      return params.change === "archived"
        ? t("notifications.type.knowledge_fact_archived", { label })
        : t("notifications.type.knowledge_fact_changed", {
            label,
            old: String(params.old_display ?? ""),
            new: String(params.new_display ?? ""),
          });
    case "conversation.needs_human":
      return t("notifications.type.conversation_needs_human");
    case "reply.failed":
      return t("notifications.type.reply_failed");
    case "account.needs_reauth":
      return t("notifications.type.account_needs_reauth");
    default:
      return t("notifications.type.unknown");
  }
}
