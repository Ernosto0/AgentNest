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
    case "content.on_hold": {
      // Params carry the internal title and a reason code, never the caption (observability §4.3).
      const title = String(params.title ?? "");
      const reason = String(params.reason ?? "");
      return reason === "FACT_CHANGED" || reason === "ACCOUNT_UNAVAILABLE"
        ? t(`notifications.type.content_on_hold_${reason}`, { title })
        : t("notifications.type.content_on_hold", { title });
    }
    case "content.published":
      return t("notifications.type.content_published", { title: String(params.title ?? "") });
    case "content.failed": {
      const code = String(params.reason ?? "");
      const known = code !== "" ? t(`errors.${code}.what`, { defaultValue: "" }) : "";
      return t("notifications.type.content_failed", {
        title: String(params.title ?? ""),
        what: known !== "" ? known : t("content.failure.unknown.what"),
      });
    }
    case "conversation.needs_human":
      return t("notifications.type.conversation_needs_human");
    case "reply.failed":
      return t("notifications.type.reply_failed");
    case "account.needs_reauth":
      return t("notifications.type.account_needs_reauth");
    case "account.degraded":
      return t("notifications.type.account_degraded");
    case "account.recovered":
      return t("notifications.type.account_recovered");
    case "account.permission_missing": {
      const capability = String(params.capability ?? "");
      const known = ["messaging", "publish_feed_image", "publish_story_image"].includes(capability);
      return t("notifications.type.account_permission_missing", {
        what: t(`notifications.capability.${known ? capability : "unknown"}`),
      });
    }
    case "report.daily_ready":
      return t("notifications.type.report_daily_ready", { date: String(params.local_date ?? "") });
    case "member.joined":
      return t("notifications.type.member_joined", { name: String(params.display_name ?? "") });
    default:
      return t("notifications.type.unknown");
  }
}
