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
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold tracking-wide text-purple-800 ring-1 ring-purple-600 ring-inset ${className}`}
    >
      {t("badge.simulated")}
    </span>
  );
}
