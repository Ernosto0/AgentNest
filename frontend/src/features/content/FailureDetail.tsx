import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { Button } from "@/components/Button";
import { CriticalIcon, HourglassIcon } from "@/components/icons";
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
      className={`flex flex-col gap-3 rounded-panel border p-5 text-body shadow-xs ${
        failed
          ? "border-danger bg-danger-subtle text-danger"
          : "border-info bg-info-subtle text-info"
      }`}
    >
      <div className="flex items-center gap-2.5">
        {failed ? (
          <CriticalIcon className="text-xl shrink-0" />
        ) : (
          <HourglassIcon className="text-xl shrink-0 motion-safe:animate-pulse" />
        )}
        <h2 className="font-heading font-bold text-base">{t("content.failure.title")}</h2>
      </div>

      <div className="flex flex-col gap-1.5 pl-0.5">
        <p className="font-medium">{what}</p>
        {/* A retryable code on a failed item means the retries ran out: its "we will try again" must not show. */}
        <p className="opacity-90">{failed && AUTO_RETRY.has(code) ? t("content.failure.exhausted") : next}</p>
      </div>

      {retrying ? (
        <div className="flex items-center gap-2 pt-1">
          <p data-testid="failure-retry" className="font-semibold text-sm">
            {time
              ? t("content.failure.retryAt", { time, attempts: item.operation?.attempts ?? 0 })
              : t("content.failure.retryAuto")}
          </p>
        </div>
      ) : null}

      {failed ? (
        <p data-testid="failure-final" className="font-semibold text-sm pt-1">
          {t("content.failure.noRetry")}
        </p>
      ) : null}

      {failed ? (
        <div className="pt-2">
          <Button onClick={onEdit} className="shadow-xs">
            {t("content.actions.editResend")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
