import type { AppNotification } from "@/api/types";

/** Where a notification leads, or null when there is nowhere to go. */
export function notificationTarget(workspaceId: string, notification: AppNotification): string | null {
  const base = `/w/${workspaceId}`;
  const params = notification.params as Record<string, unknown>;
  if (notification.type.startsWith("owner_question.")) {
    const account = params.account_id;
    const question = params.question_id;
    return typeof account === "string" && typeof question === "string" ? `${base}/more/agent/questions/${encodeURIComponent(question)}?account=${encodeURIComponent(account)}` : `${base}/more/agent/questions`;
  }
  if (notification.type.startsWith("approval.")) return `${base}/approvals`;
  if (notification.type.startsWith("content.")) {
    const id = params.content_id;
    return typeof id === "string" ? `${base}/content/${id}` : `${base}/content`;
  }
  if (notification.type === "knowledge.fact_changed" || notification.type === "knowledge.promotion_expired") {
    return `${base}/more/knowledge`;
  }
  if (notification.type === "conversation.needs_human" || notification.type === "reply.failed") {
    const id = params.conversation_id;
    return typeof id === "string" ? `${base}/inbox/${id}` : `${base}/inbox`;
  }
  if (notification.type.startsWith("account.")) return `${base}/more/settings/connections`;
  if (notification.type === "member.joined") return `${base}/more/settings/members`;
  if (notification.type === "report.daily_ready") {
    const day = params.local_date;
    return typeof day === "string" ? `${base}/more/reports?date=${day}` : `${base}/more/reports`;
  }
  return null;
}
