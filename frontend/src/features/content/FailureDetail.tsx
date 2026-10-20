import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AUTO_RETRY, failureCode, failureText } from "./failure";

/**
 * The reason a post is not out, in plain language, with what happens next: a retry says when,
 * a final failure says that nothing more will be tried and offers to edit and send again. An
 * attempt whose result is not known reads "we are checking" and offers nothing (never resend).
 */
export function FailureDetail({ item, onEdit }: { item: ContentItem; onEdit: () => void }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const code = failureCode(item);
  if (code === null) return null;
  const { what, next } = failureText(code, t);

  const nextAttempt = item.operation?.next_attempt_at ?? null;
  const time = nextAttempt
    ? new Date(nextAttempt).toLocaleTimeString(i18n.language, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: workspace.timezone,
      })
    : null;
  const failed = item.status === "failed";
  const retrying = item.status === "retry_scheduled";

  return (
    <section
      aria-label={t("content.failure.title")}
      data-testid="failure-detail"
      data-code={code}
      className={`flex flex-col gap-2 rounded-xl p-4 ring-1 ${
        failed ? "bg-red-50 text-red-900 ring-red-300" : "bg-blue-50 text-blue-900 ring-blue-300"
      }`}
    >
      <h2 className="font-semibold">{t("content.failure.title")}</h2>
      <p>{what}</p>
      {/* A retryable code on a failed item means the retries ran out: its "we will try again" must not show. */}
      <p>{failed && AUTO_RETRY.has(code) ? t("content.failure.exhausted") : next}</p>
      {retrying ? (
        <p data-testid="failure-retry" className="font-medium">
          {time
            ? t("content.failure.retryAt", { time, attempts: item.operation?.attempts ?? 0 })
            : t("content.failure.retryAuto")}
        </p>
      ) : null}
      {failed ? (
        <p data-testid="failure-final" className="font-medium">
          {t("content.failure.noRetry")}
        </p>
      ) : null}
      {failed ? (
        <div>
          <Button onClick={onEdit}>{t("content.actions.editResend")}</Button>
        </div>
      ) : null}
    </section>
  );
}
