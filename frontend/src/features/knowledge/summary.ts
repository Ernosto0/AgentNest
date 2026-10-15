import type { Fact, FactCategory, TemplateItem } from "@/api/types";
import { CATEGORY_ORDER } from "./labels";

export interface CategorySummary {
  category: FactCategory;
  verified: number;
  /** Unverified, contested, expired or not yet started: the owner has something to do. */
  attention: number;
  /** Fixed template items (and required pattern items) that have no fact yet. */
  missing: number;
}

const ACTIVE = (fact: Fact) => fact.status !== "archived";

/** Per-category counts for the knowledge overview. Categories with nothing to show are omitted. */
export function summarize(template: TemplateItem[], facts: Fact[]): CategorySummary[] {
  const categories = new Set<FactCategory>(["custom"]);
  for (const item of template) categories.add(item.category);
  for (const fact of facts) if (ACTIVE(fact)) categories.add(fact.category);

  return CATEGORY_ORDER.filter((category) => categories.has(category)).map((category) => {
    const inCategory = facts.filter((fact) => fact.category === category && ACTIVE(fact));
    const verified = inCategory.filter((fact) => fact.state === "verified").length;
    const missing = template.filter(
      (item) =>
        item.category === category &&
        item.status === "missing" &&
        (item.key !== null || item.required_for !== null),
    ).length;
    return { category, verified, attention: inCategory.length - verified, missing };
  });
}

export type Entry =
  | { kind: "fixed"; item: TemplateItem; fact: Fact | null }
  | { kind: "pattern"; item: TemplateItem; facts: Fact[] }
  | { kind: "other"; facts: Fact[] };

/** What the category screen lists, in template order; facts no template item claims go last. */
export function categoryEntries(
  category: FactCategory,
  template: TemplateItem[],
  facts: Fact[],
): { entries: Entry[]; archived: Fact[] } {
  const live = facts.filter((fact) => fact.category === category && ACTIVE(fact));
  const claimed = new Set<string>();
  const entries: Entry[] = [];
  for (const item of template.filter((i) => i.category === category)) {
    if (item.key !== null) {
      const fact = live.find((f) => f.key === item.key) ?? null;
      if (fact) claimed.add(fact.id);
      entries.push({ kind: "fixed", item, fact });
    } else {
      const prefix = (item.pattern ?? "").replace(/\*$/, "");
      const matching = live.filter((f) => prefix !== "" && f.key.startsWith(prefix));
      for (const fact of matching) claimed.add(fact.id);
      entries.push({ kind: "pattern", item, facts: matching });
    }
  }
  const others = live.filter((fact) => !claimed.has(fact.id));
  if (others.length > 0 || category === "custom") entries.push({ kind: "other", facts: others });
  return {
    entries,
    archived: facts.filter((fact) => fact.category === category && !ACTIVE(fact)),
  };
}
