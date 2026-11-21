import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { Button } from "@/components/Button";
import { HelpCircleIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { tourIdForPath } from "./tours";
import { useTour } from "./useTour";

/** Header help trigger that runs the Driver.js guide for the active page. */
export function PageGuideButton() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const location = useLocation();
  const prefix = `/w/${workspace.id}`;
  const path = location.pathname === prefix ? "" : location.pathname.slice(prefix.length + 1);
  const tourId = tourIdForPath(path);
  const { start, hasTour } = useTour(tourId);

  if (!tourId || !hasTour) return null;

  return (
    <Button
      variant="ghost"
      onClick={start}
      aria-label={t("tour.openGuide")}
      title={t("tour.openGuide")}
      data-testid="page-guide-button"
      className="min-w-11 rounded-xl border border-transparent px-2.5 text-secondary hover:border-border/80 hover:bg-surface-subtle hover:text-primary"
    >
      <HelpCircleIcon className="text-xl" />
    </Button>
  );
}
