import { useTranslation } from "react-i18next";

const text = (summary: Record<string, unknown>, key: string): string => {
  const value = summary[key];
  return typeof value === "string" ? value : "";
};

/**
 * What the "make a price card" confirmation would create: the price comes from the verified fact
 * (formatted by the server), and the card only becomes a draft with an image: nothing is approved,
 * scheduled or published.
 */
export function PriceCardSummary({ summary }: { summary: Record<string, unknown> }) {
  const { t } = useTranslation();
  const format = text(summary, "format") === "feed" ? "feed" : "story";
  return (
    <div className="flex flex-col gap-3 rounded-panel border border-border bg-surface p-4 shadow-xs" data-testid="price-card-summary">
      <p className="font-heading text-base font-bold text-primary break-words">{text(summary, "label")}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-secondary">{t("command.confirm.makePriceCard.price")}</dt>
        <dd className="font-semibold text-primary">{text(summary, "price_formatted")}</dd>
        <dt className="text-secondary">{t("command.confirm.makePriceCard.format")}</dt>
        <dd className="text-primary">{t(`content.template.format.${format}`)}</dd>
      </dl>
      <p className="text-sm text-secondary">{t("command.confirm.makePriceCard.consequence")}</p>
    </div>
  );
}
