import { useTranslation } from "react-i18next";
import { formatVerifiedDate } from "./formatVerifiedDate";

/** What every "facts used" list needs: the value as shown, the fact it came from, when it was verified. */
export interface FactSource {
  label: string;
  display: string;
  verified_at: string | null;
}

/**
 * The verified facts a reply used, each as "value, from: label, verified date". Shared by the test
 * chat and, later, by the inbox and approvals (D-01), so it takes plain data and no API types.
 * Renders nothing for an empty list unless `emptyLabel` is set.
 */
export function FactsUsed({
  facts,
  timeZone,
  emptyLabel,
  className = "",
}: {
  facts: readonly FactSource[];
  timeZone?: string;
  emptyLabel?: string;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  if (facts.length === 0) {
    return emptyLabel ? (
      <p data-testid="facts-used-empty" className={`text-metadata text-secondary ${className}`}>{emptyLabel}</p>
    ) : null;
  }
  return (
    <div data-testid="facts-used" className={`min-w-0 ${className}`}>
      <p className="text-metadata font-semibold text-secondary">{t("factsUsed.title")}</p>
      <ul className="mt-1.5 flex min-w-0 flex-col gap-1.5">
        {facts.map((fact, index) => {
          const date = fact.verified_at ? formatVerifiedDate(fact.verified_at, i18n.language, timeZone) : "";
          return (
            <li key={`${fact.label}:${index}`} data-testid="fact-used" className="min-w-0 rounded-control border border-success/40 bg-success-subtle px-3 py-2 text-body">
              <span className="font-semibold text-success [overflow-wrap:anywhere]">{fact.display}</span>
              <span className="block text-metadata text-secondary [overflow-wrap:anywhere]">
                {date ? t("factsUsed.line", { label: fact.label, date }) : t("factsUsed.lineNoDate", { label: fact.label })}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
