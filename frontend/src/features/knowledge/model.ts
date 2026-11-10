import type { Fact, FactCandidate, FactCategory, Readiness, Requirement, TemplateItem } from "@/api/types";
import { CATEGORY_ORDER } from "./labels";

/**
 * Derived views of the knowledge base. Everything here is computed from what the API returns
 * (facts, template checklist, candidates, readiness); nothing is estimated or scored.
 */

/** Categories as an owner thinks about them: the basics, what is offered, how to answer. */
export const CATEGORY_GROUPS: { id: "basics" | "offer" | "answers"; categories: FactCategory[] }[] = [
  { id: "basics", categories: ["identity", "contact", "location", "hours"] },
  { id: "offer", categories: ["service", "pricing", "promotion", "booking", "schedule"] },
  { id: "answers", categories: ["policy", "faq", "brand", "escalation", "custom"] },
];

/** Facts that exist but are not used yet because the owner has to look at them. */
const REVIEW_STATES = new Set<Fact["state"]>(["unverified", "contested", "expired"]);

export const isLive = (fact: Fact) => fact.status !== "archived";
export const needsReview = (fact: Fact) => isLive(fact) && REVIEW_STATES.has(fact.state);

/** Anchors used by deep links from the overview into a category page. */
export const factAnchor = (key: string) => `fact-${key}`;
export const itemAnchor = (identifier: string) => `item-${identifier}`;

/** Readiness requirements about business knowledge that are not satisfied yet. */
export function openKnowledgeRequirements(readiness: Readiness | undefined): Requirement[] {
  return (readiness?.requirements ?? []).filter((r) => !r.satisfied && r.link.target === "knowledge");
}

/**
 * Template identifiers that block readiness right now (from the server's `missing_keys`), or
 * null while readiness is unknown. A contact item is not needed once another contact exists,
 * and the "do not share prices" answer is not needed when prices are shared.
 */
export function neededIdentifiers(readiness: Readiness | undefined): Set<string> | null {
  if (!readiness) return null;
  return new Set(openKnowledgeRequirements(readiness).flatMap((r) => r.missing_keys));
}

/** What a template item is for right now: blocking setup, or optional. */
export function isNeeded(item: TemplateItem, needed: Set<string> | null): boolean {
  // Without readiness, fall back to the template's own (unconditional) requirement.
  if (needed === null) return item.required_for !== null && item.required_when === null && item.required_group === null;
  return needed.has(item.identifier);
}

/**
 * A template item with no fact that is worth listing as "not added": every fixed item, and a
 * pattern item (services, prices) only when it is required at all. Conditional items whose
 * condition does not apply (e.g. the price answer when prices are shared) are left out.
 */
function countsAsNotAdded(item: TemplateItem, needed: Set<string> | null): boolean {
  if (item.status !== "missing") return false;
  if (item.key === null && item.required_for === null) return false;
  if (item.required_when !== null && !needed?.has(item.identifier)) return false;
  return true;
}

export interface CategorySummary {
  category: FactCategory;
  /** Live facts that are verified and in use now. */
  verified: number;
  /** Unverified, contested or expired facts: not used until the owner acts. */
  review: number;
  /** Verified facts whose validity window has not started yet. */
  upcoming: number;
  /** Suggested template items with no fact yet (needed or optional). */
  notAdded: number;
  /** Readiness requirements this category still has to satisfy. */
  needed: Requirement[];
}

export function summarizeCategories(
  template: TemplateItem[],
  facts: Fact[],
  readiness: Readiness | undefined,
): CategorySummary[] {
  const needed = neededIdentifiers(readiness);
  const open = openKnowledgeRequirements(readiness);
  return CATEGORY_ORDER.map((category) => {
    const live = facts.filter((fact) => fact.category === category && isLive(fact));
    return {
      category,
      verified: live.filter((fact) => fact.state === "verified").length,
      review: live.filter(needsReview).length,
      upcoming: live.filter((fact) => fact.state === "not_started").length,
      notAdded: template.filter((item) => item.category === category && countsAsNotAdded(item, needed)).length,
      needed: open.filter((r) => r.link.category === category),
    };
  });
}

export interface Overview {
  verified: number;
  review: number;
  suggestions: number;
  notAdded: number;
  /** Open readiness requirements about knowledge (not the account or automation steps). */
  needed: number;
}

export function overview(
  summaries: CategorySummary[],
  candidates: FactCandidate[] | undefined,
  readiness: Readiness | undefined,
): Overview {
  const sum = (pick: (s: CategorySummary) => number) => summaries.reduce((total, s) => total + pick(s), 0);
  return {
    verified: sum((s) => s.verified),
    review: sum((s) => s.review),
    suggestions: candidates?.length ?? 0,
    notAdded: sum((s) => s.notAdded),
    needed: openKnowledgeRequirements(readiness).length,
  };
}

export type AttentionItem =
  | { kind: "needed"; requirement: Requirement; pendingFact: Fact | null }
  | { kind: "suggestions"; candidates: FactCandidate[] }
  | { kind: "fact"; fact: Fact };

const keyMatches = (identifier: string, key: string) =>
  identifier.endsWith(".*") ? key.startsWith(identifier.slice(0, -1)) : identifier === key;

/**
 * What the owner should look at, most important first: setup blockers, then suggestions, then
 * facts on hold or not yet verified, then expired ones. Facts already named by a blocker are
 * not repeated.
 */
export function attentionItems(
  facts: Fact[],
  candidates: FactCandidate[] | undefined,
  readiness: Readiness | undefined,
): AttentionItem[] {
  const items: AttentionItem[] = [];
  const covered = new Set<string>();
  for (const requirement of openKnowledgeRequirements(readiness)) {
    const pendingFact =
      facts.find((fact) => needsReview(fact) && requirement.missing_keys.some((id) => keyMatches(id, fact.key))) ?? null;
    if (pendingFact) covered.add(pendingFact.id);
    items.push({ kind: "needed", requirement, pendingFact });
  }
  if (candidates && candidates.length > 0) items.push({ kind: "suggestions", candidates });
  const rank: Partial<Record<Fact["state"], number>> = { contested: 0, unverified: 1, expired: 2 };
  const order = (fact: Fact) => CATEGORY_ORDER.indexOf(fact.category);
  facts
    .filter((fact) => needsReview(fact) && !covered.has(fact.id))
    .sort((a, b) => (rank[a.state] ?? 3) - (rank[b.state] ?? 3) || order(a) - order(b))
    .forEach((fact) => items.push({ kind: "fact", fact }));
  return items;
}

export interface NotAddedItem {
  item: TemplateItem;
  needed: boolean;
}

export interface CategoryView {
  /** Live facts in template order: fixed items first, then owner-named ones, then the rest. */
  facts: Fact[];
  /** Template items with no fact yet; the ones that block setup come first. */
  notAdded: NotAddedItem[];
  /** Owner-named kinds (services, prices, FAQs…) the owner can add more of. */
  patterns: TemplateItem[];
  archived: Fact[];
}

export function categoryView(
  category: FactCategory,
  template: TemplateItem[],
  facts: Fact[],
  needed: Set<string> | null,
): CategoryView {
  const items = template.filter((item) => item.category === category);
  const live = facts.filter((fact) => fact.category === category && isLive(fact));
  const fixedOrder = new Map<string, number>();
  items.forEach((item, index) => {
    if (item.key !== null) fixedOrder.set(item.key, index);
  });
  const ordered = live
    .map((fact, index) => ({ fact, index }))
    .sort((a, b) => (fixedOrder.get(a.fact.key) ?? Infinity) - (fixedOrder.get(b.fact.key) ?? Infinity) || a.index - b.index)
    .map(({ fact }) => fact);

  // The same rule as the counts on the overview, so a category never lists more than it says.
  const notAdded = items
    .filter((item) => countsAsNotAdded(item, needed))
    .map((item) => ({ item, needed: isNeeded(item, needed) }))
    .sort((a, b) => Number(b.needed) - Number(a.needed));

  return {
    facts: ordered,
    notAdded,
    patterns: items.filter((item) => item.pattern !== null),
    archived: facts.filter((fact) => fact.category === category && !isLive(fact)),
  };
}

/** The template item a fact belongs to (fixed key first, then the broadest matching pattern). */
export function itemForFact(template: TemplateItem[], fact: Fact): TemplateItem | null {
  return (
    template.find((item) => item.key === fact.key) ??
    template.find((item) => item.pattern !== null && fact.key.startsWith(item.pattern.replace(/\*$/, ""))) ??
    null
  );
}

export type SearchHit = { kind: "fact"; fact: Fact } | { kind: "item"; item: TemplateItem };

/** Case- and accent-insensitive match on names (both languages) and on the value customers see. */
export function searchKnowledge(
  query: string,
  facts: Fact[],
  template: TemplateItem[],
  needed: Set<string> | null,
  language: string,
  /** The category's name in the UI language, so "prices" finds every price. */
  categoryName: (category: FactCategory) => string = () => "",
): SearchHit[] {
  const fold = (text: string) =>
    text
      .toLocaleLowerCase(language.startsWith("en") ? "en" : "tr")
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .replace(/ı/g, "i");
  const needle = fold(query.trim());
  if (needle === "") return [];
  const haystack = (...parts: string[]) => fold(parts.join(" ")).includes(needle);
  const order = (category: FactCategory) => CATEGORY_ORDER.indexOf(category);
  const factHits = facts
    .filter(isLive)
    .filter((fact) => haystack(...Object.values(fact.label), fact.display, categoryName(fact.category)))
    .sort((a, b) => order(a.category) - order(b.category))
    .map((fact): SearchHit => ({ kind: "fact", fact }));
  const itemHits = template
    .filter((item) => item.key !== null && countsAsNotAdded(item, needed))
    .filter((item) => haystack(...Object.values(item.label), categoryName(item.category)))
    .sort((a, b) => order(a.category) - order(b.category))
    .map((item): SearchHit => ({ kind: "item", item }));
  return [...factHits, ...itemHits];
}
