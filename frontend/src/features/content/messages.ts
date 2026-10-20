import type { TFunction } from "i18next";
import type { ContentCheckItem, ContentIssue } from "@/api/types";

/** Plain-language text for a submit rule (plan.md G17): our catalog first, then the server's own message. */
export function checkMessage(item: ContentCheckItem, t: TFunction): string {
  return t(`content.editor.checks.${item.code}`, {
    ...item.params,
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
