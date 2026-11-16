import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useMe } from "@/features/auth/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useEnablePush, usePushConfig } from "@/pwa/hooks";
import {
  PUSH_OPPORTUNITY_EVENT,
  dismissPushPrompt,
  hasPushOpportunity,
  needsHomeScreenInstall,
  pushPermission,
  pushPromptDismissed,
  pushSupported,
  storedDeviceId,
} from "@/pwa/push";

/** The short "Add to Home Screen" steps: iOS delivers pushes only to an installed web app. */
export function IosInstallGuide() {
  const { t } = useTranslation();
  return (
    <div data-testid="push-ios-guide" className="flex min-w-0 flex-col gap-2">
      <p className="font-semibold text-primary">{t("push.ios.title")}</p>
      <ol className="list-decimal space-y-1 pl-5 text-body text-secondary">
        <li>{t("push.ios.step1")}</li>
        <li>{t("push.ios.step2")}</li>
        <li>{t("push.ios.step3")}</li>
      </ol>
      <p className="text-metadata text-secondary">{t("push.ios.note")}</p>
    </div>
  );
}

/**
 * Offered once, right after the owner's first approval (never on first load): turn on phone
 * notifications, or on iOS Safari outside the installed app, add the app to the Home Screen first.
 * Hidden when the server has no push keys, when the browser cannot receive pushes, when the
 * permission was already refused (nothing left to ask; Settings explains), when the device is
 * already registered, and once dismissed.
 */
export function PushPrompt() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const me = useMe();
  const userId = me.data?.user.id ?? "";
  const [, bump] = useState(0);
  const [done, setDone] = useState(false);
  const enable = useEnablePush(workspace.id);

  useEffect(() => {
    const refresh = () => bump((n) => n + 1);
    window.addEventListener(PUSH_OPPORTUNITY_EVENT, refresh);
    return () => window.removeEventListener(PUSH_OPPORTUNITY_EVENT, refresh);
  }, []);

  const waiting =
    userId !== "" &&
    hasPushOpportunity(userId, workspace.id) &&
    !pushPromptDismissed(userId, workspace.id) &&
    storedDeviceId(userId, workspace.id) === null;
  // The key request is only made once the moment has come: nothing loads for a new user.
  const config = usePushConfig(workspace.id, waiting || done);

  if (done) {
    return (
      <PromptFrame>
        <p role="status" className="min-w-0 flex-1 text-body text-primary">
          {t("push.prompt.done")}
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/w/${workspace.id}/more/settings/connections`}
            className="inline-flex min-h-11 items-center rounded-control px-3 text-body font-semibold text-action hover:bg-surface-subtle"
          >
            {t("push.prompt.settings")}
          </Link>
          <Button variant="secondary" onClick={() => setDone(false)}>
            {t("push.prompt.close")}
          </Button>
        </div>
      </PromptFrame>
    );
  }
  if (!waiting || !config.data?.enabled) return null;

  const dismiss = () => {
    dismissPushPrompt(userId, workspace.id);
    bump((n) => n + 1);
  };

  if (needsHomeScreenInstall()) {
    return (
      <PromptFrame>
        <div className="min-w-0 flex-1">
          <IosInstallGuide />
        </div>
        <Button variant="secondary" onClick={dismiss}>
          {t("push.ios.dismiss")}
        </Button>
      </PromptFrame>
    );
  }
  // Nothing to offer: no push in this browser, or the permission was already refused.
  if (!pushSupported() || pushPermission() === "denied") return null;

  const outcome = enable.data && enable.data.status !== "subscribed" ? enable.data.status : null;
  return (
    <PromptFrame>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-primary">{t("push.prompt.title")}</p>
        <p className="mt-1 text-body text-secondary">{t("push.prompt.body")}</p>
        {outcome ? (
          <p role="alert" className="mt-2 text-body text-danger">
            {t(`push.outcome.${outcome}`)}
          </p>
        ) : null}
        {enable.error ? <ErrorMessage error={enable.error} /> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={enable.isPending}
          onClick={() =>
            enable.mutate(
              { approvals: true },
              { onSuccess: (result) => result.status === "subscribed" && setDone(true) },
            )
          }
        >
          {enable.isPending ? t("push.prompt.enabling") : t("push.prompt.enable")}
        </Button>
        <Button variant="secondary" disabled={enable.isPending} onClick={dismiss}>
          {t("push.prompt.later")}
        </Button>
      </div>
    </PromptFrame>
  );
}

function PromptFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t("push.prompt.label")}
      data-testid="push-prompt"
      className="mx-4 mt-4 flex min-w-0 flex-col gap-4 rounded-panel border border-border bg-surface p-4 shadow-xs sm:flex-row sm:items-center md:mx-6 min-[1200px]:mx-8"
    >
      {children}
    </section>
  );
}
