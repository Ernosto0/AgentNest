import { useTranslation } from "react-i18next";
import { useCurrentWorkspace } from "@/features/workspaces/context";

/** Demo workspace context never establishes provenance of individual results. */
export function SimulationBanner({ offline = false }: { offline?: boolean }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  if (!workspace.is_demo && !offline) return null;
  return <aside aria-label={t("shell.environment")} className="border-b border-border bg-surface-subtle px-4 py-2 text-metadata text-secondary md:px-6 min-[1200px]:px-8">
    {workspace.is_demo ? <details data-testid="simulation-banner" className="group">
      <summary className="cursor-pointer rounded-control py-1 font-medium text-primary focus-visible:outline-2 focus-visible:outline-focus">{t("banner.simulation")}{offline ? <span data-testid="ai-mode" className="font-normal text-secondary"> · {t("shell.offlineShort")}</span> : null}</summary>
      <p className="mt-1 max-w-prose pb-1">{t("banner.simulationDetail")}{offline ? <> {t("aiMode.offline")}</> : null}</p>
    </details> : <p data-testid="ai-mode">{t("aiMode.offline")}</p>}
  </aside>;
}
