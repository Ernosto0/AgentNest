import { useTranslation } from "react-i18next";

/**
 * Mandatory wherever simulated data is shown (INV-09). Purple outline, appended to any status.
 * The word is the signal; colour only reinforces it.
 */
export function SimulatedBadge({ className = "" }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <span
      data-testid="simulated-badge"
      className={`inline-flex items-center rounded-full bg-simulation-subtle px-2 py-1 text-metadata font-semibold tracking-wide text-simulation ring-1 ring-simulation ring-inset ${className}`}
    >
      {t("badge.simulated")}
    </span>
  );
}
