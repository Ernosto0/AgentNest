import { useTranslation } from "react-i18next";

/** Persistent notice on demo workspaces (INV-09): simulated data is never presented as real. */
export function SimulationBanner() {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      data-testid="simulation-banner"
      className="border-b border-purple-300 bg-purple-50 px-4 py-2 text-sm text-purple-950"
    >
      <p className="font-semibold">{t("banner.simulation")}</p>
      <p className="text-purple-900">{t("banner.simulationDetail")}</p>
    </div>
  );
}
