import { describe, expect, it } from "vitest";
import enKnowledge from "@/i18n/locales/en/knowledge.json";
import trKnowledge from "@/i18n/locales/tr/knowledge.json";
import { CATEGORY_ORDER } from "./labels";
import { VALUE_TYPES } from "./editors/valueTypes";
import { DAYS } from "./editors/hoursModel";

// `npm run i18n:check` verifies literal t("key") calls. These keys are built at run time
// (t(`knowledge.state.${state}`)), so every value they can take is pinned here.
const DYNAMIC: Record<string, readonly string[]> = {
  "knowledge.category": CATEGORY_ORDER,
  "knowledge.state": ["verified", "unverified", "contested", "expired", "not_started", "archived", "missing", "present"],
  "knowledge.source": ["owner_entry", "owner_command", "candidate_accepted", "seed", "template_default"],
  "knowledge.candidateSource": ["pasted_text", "staff_proposal", "instagram_profile", "website"],
  "knowledge.valueType": VALUE_TYPES,
  "knowledge.days": DAYS,
  "knowledge.unit": ["none", "month", "session", "package", "item", "hour", "person", "day", "year"],
  "knowledge.criticality": ["standard", "critical"],
  "knowledge.required": ["drafts", "ready"],
  "knowledge.bool": ["true", "false"],
  "knowledge.enum": ["share", "do_not_share"],
  "knowledge.moneyError": ["invalid_number", "too_many_decimals", "unsupported_locale"],
  "knowledge.history.change": ["created", "value_changed", "verified", "archived", "restored"],
  "knowledge.fields.language": ["tr", "en"],
  "readiness.level": ["not_ready", "ready_for_drafts", "ready"],
  "readiness.status": ["missing", "not_connected", "not_reviewed"],
  "readiness.requirement": [
    "business_name", "contact", "location", "hours", "booking_instructions", "price_policy",
    "services", "account_connected", "automation_reviewed",
  ],
  "wizard.categories": [
    "beauty_wellness",
    "food_beverage",
    "retail",
    "fitness",
    "health_clinic",
    "education",
    "hospitality",
    "services",
    "other",
  ],
  "wizard.markets": ["tr", "global"],
};

function lookup(catalog: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);
}

describe.each([
  ["tr", trKnowledge],
  ["en", enKnowledge],
])("%s knowledge catalog", (_language, catalog) => {
  it.each(Object.entries(DYNAMIC))("has every value of %s", (prefix, values) => {
    for (const value of values) {
      const text = lookup(catalog, `${prefix}.${value}`);
      expect(typeof text, `${prefix}.${value}`).toBe("string");
      expect(text, `${prefix}.${value}`).not.toBe("");
    }
  });
});
