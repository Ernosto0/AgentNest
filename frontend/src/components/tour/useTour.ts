import { useCallback, useEffect, useRef } from "react";
import { driver, type DriveStep, type Driver } from "driver.js";
import { useTranslation } from "react-i18next";
import { TOURS } from "./tours";
import type { TourId } from "./types";

function isElementVisible(selector: string): boolean {
  const el = document.querySelector<HTMLElement>(selector);
  if (!el) return false;
  return el.getClientRects().length > 0;
}

/**
 * Manages an imperative Driver.js tour for a given page ID.
 * Filters out hidden targets across breakpoints and cleans up on unmount.
 */
export function useTour(tourId: TourId | null) {
  const { t } = useTranslation();
  const instance = useRef<Driver | null>(null);
  const defs = tourId ? TOURS[tourId] : undefined;
  const hasTour = Boolean(defs && defs.length > 0);

  useEffect(() => {
    return () => {
      instance.current?.destroy();
      instance.current = null;
    };
  }, [tourId]);

  const start = useCallback(() => {
    if (!defs || defs.length === 0) return;
    // Do not overlap an open modal, BottomSheet, or DestinationLauncher.
    if (document.querySelector('[role="dialog"]')) return;

    const steps: DriveStep[] = defs
      .filter((step) => isElementVisible(step.selector))
      .map((step) => ({
        element: step.selector,
        popover: {
          title: t(step.titleKey),
          description: t(step.descriptionKey),
          side: step.side,
        },
      }));

    if (steps.length === 0) return;

    instance.current?.destroy();
    instance.current = driver({
      showProgress: true,
      allowClose: true,
      nextBtnText: t("tour.next"),
      prevBtnText: t("tour.prev"),
      doneBtnText: t("tour.done"),
      steps,
    });
    instance.current.drive();
  }, [defs, t]);

  return { start, hasTour };
}
