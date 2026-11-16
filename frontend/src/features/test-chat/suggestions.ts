import type { Fact } from "@/api/types";
import { pickLabel } from "@/features/knowledge/labels";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export const MAX_SUGGESTIONS = 6;

/** A fact the assistant may actually use: verified and inside its validity window. */
const usable = (fact: Fact) => fact.usable && fact.status === "verified";

/**
 * Starter questions for the test chat, in the business language (what its customers write).
 * They are built from the business type and the labels of verified facts only. A question may
 * name a price item ("How much is Monthly membership?") but never states a price, hour or
 * contact detail: the answer has to come from the facts, which is what the owner is testing.
 *
 * Between four and six questions: a question about hours, one about price, location, booking,
 * a question typical for the business type, a complaint (to see the hand-over to a person),
 * then more fact-specific ones while there is room.
 */
export function buildSuggestions(input: {
  category: string;
  locale: string;
  facts: readonly Fact[];
  /** Translate into the business language, e.g. `i18n.getFixedT(locale)`. */
  t: Translate;
}): string[] {
  const { category, locale, facts, t } = input;
  const live = facts.filter(usable);
  const labelOf = (fact: Fact) => pickLabel(fact.label, locale);
  const prices = live.filter((f) => f.category === "pricing");
  const services = live.filter((f) => f.category === "service");
  const has = (name: Fact["category"]) => live.some((f) => f.category === name);

  const categoryKey = `testChat.suggest.category.${category}`;
  const ordered = [
    t("testChat.suggest.hours"),
    prices[0] ? t("testChat.suggest.priceItem", { item: labelOf(prices[0]) }) : t("testChat.suggest.priceGeneral"),
    t("testChat.suggest.location"),
    has("booking") || has("schedule") ? t("testChat.suggest.booking") : null,
    t(categoryKey).startsWith("testChat.") ? t("testChat.suggest.category.other") : t(categoryKey),
    t("testChat.suggest.complaint"),
    prices[1] ? t("testChat.suggest.priceItem", { item: labelOf(prices[1]) }) : null,
    services[0] ? t("testChat.suggest.serviceItem", { item: labelOf(services[0]) }) : null,
    has("contact") ? t("testChat.suggest.contact") : null,
  ];
  const seen = new Set<string>();
  return ordered
    .filter((text): text is string => !!text && !seen.has(text) && !!seen.add(text))
    .slice(0, MAX_SUGGESTIONS);
}
