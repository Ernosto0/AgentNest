import type { Conversation } from "@/api/types";

/** The label of a customer: the handle if known, else a short stable number. */
export function customerLabel(
  conversation: Pick<Conversation, "customer_handle" | "customer_number">,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  return conversation.customer_handle ?? t("convo.customer", { number: conversation.customer_number });
}
