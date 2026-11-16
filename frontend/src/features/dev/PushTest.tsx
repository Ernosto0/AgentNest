import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AppError } from "@/api/errors";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  pushSupported,
  subscribeThisDevice,
  unsubscribeThisDevice,
  type PushOutcome,
} from "@/pwa/push";

/** Developer test for F-01 part 1: store this browser's push subscription. Sends nothing. */
export function PushTest({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const [outcome, setOutcome] = useState<PushOutcome | "removed" | null>(null);
  const subscribe = useMutation<PushOutcome, AppError>({
    mutationFn: () => subscribeThisDevice(workspaceId),
    onSuccess: setOutcome,
  });
  const unsubscribe = useMutation<void, AppError, string>({
    mutationFn: (id) => unsubscribeThisDevice(workspaceId, id),
    onSuccess: () => setOutcome("removed"),
  });

  const subscribed = outcome && outcome !== "removed" && outcome.status === "subscribed" ? outcome : null;
  const message =
    outcome === "removed"
      ? t("devPanel.push.removed")
      : outcome && outcome.status === "subscribed"
        ? t("devPanel.push.subscribed", { label: outcome.label })
        : outcome
          ? t(`devPanel.push.${outcome.status}`)
          : !pushSupported()
            ? t("devPanel.push.unsupported")
            : null;

  return (
    <div className="flex min-w-0 flex-col gap-4 border-t border-border pt-6 xl:col-span-2" data-testid="dev-push">
      <h2 className="text-base font-heading font-semibold text-primary">{t("devPanel.push.title")}</h2>
      <p className="text-xs text-secondary leading-relaxed">{t("devPanel.push.hint")}</p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          data-testid="dev-push-subscribe"
          pending={subscribe.isPending}
          onClick={() => subscribe.mutate()}
        >
          {t("devPanel.push.subscribe")}
        </Button>
        {subscribed ? (
          <Button
            variant="ghost"
            data-testid="dev-push-unsubscribe"
            pending={unsubscribe.isPending}
            onClick={() => unsubscribe.mutate(subscribed.id)}
          >
            {t("devPanel.push.unsubscribe")}
          </Button>
        ) : null}
      </div>
      {message ? (
        <p className="text-sm text-primary" role="status">
          {message}
        </p>
      ) : null}
      {subscribe.error ? <ErrorMessage error={subscribe.error} /> : null}
      {unsubscribe.error ? <ErrorMessage error={unsubscribe.error} /> : null}
    </div>
  );
}
