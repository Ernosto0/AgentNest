import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { HelpCircleIcon, XIcon } from "@/components/icons";
import { useTour } from "@/components/tour/useTour";

const STORAGE_PREFIX = "pivoris.tour.homeSeen.";

function readSeen(workspaceId: string): boolean {
  try {
    return window.localStorage.getItem(`${STORAGE_PREFIX}${workspaceId}`) === "1";
  } catch {
    return false;
  }
}

function writeSeen(workspaceId: string): void {
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${workspaceId}`, "1");
  } catch {
    // Storage can be blocked in private browsing; dismissing for this session still works.
  }
}

/** Dismissible first-visit prompt offering the 30-second Home tour. */
export function HomeWelcomePrompt({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const { start, hasTour } = useTour("home");
  const [dismissed, setDismissed] = useState(() => readSeen(workspaceId));

  if (dismissed || !hasTour) return null;

  const dismiss = () => {
    writeSeen(workspaceId);
    setDismissed(true);
  };

  const handleStart = () => {
    dismiss();
    start();
  };

  return (
    <div
      data-testid="home-tour-prompt"
      className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-assistant/70 px-4 py-3 sm:px-5"
    >
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface text-action ring-1 ring-border">
          <HelpCircleIcon className="text-base" />
        </span>
        <div className="min-w-0">
          <p className="font-heading text-body font-semibold text-primary">{t("tour.welcomeTitle")}</p>
          <p className="text-metadata text-secondary">{t("tour.welcomeBody")}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button onClick={handleStart}>
          {t("tour.startTour")}
        </Button>
        <Button variant="ghost" onClick={dismiss} aria-label={t("tour.dismiss")}>
          <XIcon className="text-base" />
          <span className="sr-only sm:not-sr-only">{t("tour.dismiss")}</span>
        </Button>
      </div>
    </div>
  );
}
