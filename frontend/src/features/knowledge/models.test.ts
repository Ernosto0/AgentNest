import { describe, expect, it } from "vitest";
import { candidate, fact, templateItem } from "@/test/fixtures";
import { buildHours, rowsFromValue } from "./editors/hoursModel";
import type { Readiness, Requirement } from "@/api/types";
import { CATEGORY_ORDER, slugFromLabel } from "./labels";
import { attentionItems, categoryView, neededIdentifiers, overview, searchKnowledge, summarizeCategories } from "./model";

describe("hours editor model", () => {
  const weekly = {
    mon: [["07:00", "23:00"]],
    tue: [["07:00", "23:00"]],
    wed: [["07:00", "23:00"]],
    thu: [["07:00", "23:00"]],
    fri: [["07:00", "23:00"]],
    sat: [["09:00", "21:00"]],
    sun: [],
    exceptions: [{ date: "2026-10-29", closed: true, ranges: [] }],
  };

  it("groups days with identical hours into one row and leaves closed days out", () => {
    const rows = rowsFromValue(weekly);
    expect(rows).toEqual([
      { days: ["mon", "tue", "wed", "thu", "fri"], ranges: [["07:00", "23:00"]] },
      { days: ["sat"], ranges: [["09:00", "21:00"]] },
    ]);
  });

  it("round-trips to the canonical value", () => {
    expect(buildHours(rowsFromValue(weekly), [{ date: "2026-10-29", closed: true, ranges: [] }])).toEqual(weekly);
  });

  it("is incomplete (null) while a range is empty or reversed, or an exception has no date", () => {
    expect(buildHours([{ days: ["mon"], ranges: [["", "10:00"]] }], [])).toBeNull();
    expect(buildHours([{ days: ["mon"], ranges: [["10:00", "09:00"]] }], [])).toBeNull();
    expect(buildHours([], [{ date: "", closed: true, ranges: [] }])).toBeNull();
    expect(buildHours([], [{ date: "2026-12-25", closed: false, ranges: [] }])).toBeNull();
  });
});

describe("knowledge model", () => {
  const template = [
    templateItem({ identifier: "a", key: "pricing.membership_monthly" }),
    templateItem({ identifier: "b", key: "pricing.student_monthly", status: "unverified" }),
    templateItem({ identifier: "pricing.single_session", key: "pricing.single_session", label: { tr: "Tek seans", en: "Single session" }, status: "missing" }),
    templateItem({
      identifier: "service.*", key: null, pattern: "service.*", category: "service",
      status: "missing", required_for: "ready", value_types: ["localized_text"],
    }),
    templateItem({
      identifier: "faq.*", key: null, pattern: "faq.*", category: "faq", status: "missing",
      value_types: ["localized_text"],
    }),
    templateItem({
      identifier: "contact.phone", key: "contact.phone", label: { tr: "Telefon", en: "Phone" }, category: "contact", status: "missing",
      required_for: "drafts", required_group: "contact",
    }),
    templateItem({
      identifier: "contact.email", key: "contact.email", label: { tr: "E-posta", en: "Email" }, category: "contact", status: "missing",
      required_for: "drafts", required_group: "contact",
    }),
    templateItem({
      identifier: "policy.price_answer_text", key: "policy.price_answer_text", label: { tr: "Fiyat sorusuna yanıt", en: "Answer to price questions" }, category: "policy",
      status: "missing", required_for: "ready", required_when: "price_disclosure=do_not_share",
    }),
  ];
  const facts = [
    fact(),
    fact({ id: "2", key: "pricing.student_monthly", label: { tr: "Öğrenci aylık", en: "Student monthly" }, display: "4.500 ₺ / ay", state: "unverified", status: "unverified" }),
    fact({ id: "3", key: "pricing.old", status: "archived", state: "archived" }),
  ];
  const requirement = (code: string, category: string, missing: string[], required_for: "drafts" | "ready" = "ready"): Requirement => ({
    code, required_for, satisfied: false, status: "missing",
    link: { target: "knowledge", category, key: missing[0] ?? null }, missing_keys: missing,
  });
  const readiness: Readiness = {
    level: "not_ready",
    requirements: [
      requirement("contact", "contact", ["contact.phone", "contact.whatsapp", "contact.email"], "drafts"),
      requirement("services", "service", ["service.*"]),
      { code: "account_connected", required_for: "ready", satisfied: false, status: "not_connected", link: { target: "integrations", category: null, key: null }, missing_keys: [] },
    ],
  };

  it("counts verified, to-review and not-added facts per category, in the fixed category order", () => {
    const summaries = summarizeCategories(template, facts, readiness);
    expect(summaries.map((s) => s.category)).toEqual(CATEGORY_ORDER);
    expect(summaries.find((s) => s.category === "pricing")).toMatchObject({ verified: 1, review: 1, notAdded: 1, needed: [] });
    // a required pattern item with no fact counts as not added; an optional one does not
    expect(summaries.find((s) => s.category === "service")?.notAdded).toBe(1);
    expect(summaries.find((s) => s.category === "faq")?.notAdded).toBe(0);
    // a conditional item whose condition does not apply is not counted
    expect(summaries.find((s) => s.category === "policy")?.notAdded).toBe(0);
  });

  it("marks only what readiness is waiting for as needed, never the optional template items", () => {
    const needed = neededIdentifiers(readiness);
    const contact = categoryView("contact", template, facts, needed);
    expect(contact.notAdded.map((n) => [n.item.identifier, n.needed])).toEqual([
      ["contact.phone", true],
      ["contact.email", true],
    ]);
    const pricing = categoryView("pricing", template, facts, needed);
    expect(pricing.notAdded).toEqual([{ item: expect.objectContaining({ identifier: "pricing.single_session" }), needed: false }]);
    // once another contact exists, the server no longer lists these keys: they become optional
    const satisfied = neededIdentifiers({ level: "ready", requirements: [] });
    expect(categoryView("contact", template, facts, satisfied).notAdded.every((n) => !n.needed)).toBe(true);
  });

  it("lists live facts in template order and keeps archived ones apart", () => {
    const view = categoryView("pricing", template, [fact({ id: "9", key: "pricing.zz_custom" }), ...facts], null);
    expect(view.facts.map((f) => f.key)).toEqual(["pricing.membership_monthly", "pricing.student_monthly", "pricing.zz_custom"]);
    expect(view.archived.map((f) => f.key)).toEqual(["pricing.old"]);
    expect(categoryView("service", template, facts, null).patterns.map((i) => i.identifier)).toEqual(["service.*"]);
  });

  it("orders attention: setup blockers, then suggestions, then facts on hold or unverified", () => {
    const pending = fact({ id: "s1", key: "service.reformer", category: "service", state: "unverified", status: "unverified" });
    const contested = fact({ id: "c1", key: "pricing.single_session", state: "contested" });
    const items = attentionItems([...facts, pending, contested], [candidate()], readiness);
    expect(items.map((i) => (i.kind === "needed" ? `needed:${i.requirement.code}` : i.kind === "fact" ? `fact:${i.fact.key}` : i.kind))).toEqual([
      "needed:contact",
      "needed:services",
      "suggestions",
      "fact:pricing.single_session",
      "fact:pricing.student_monthly",
    ]);
    // the unverified service is what the services requirement waits for, so it is not repeated
    expect(items[1]).toMatchObject({ kind: "needed", pendingFact: { key: "service.reformer" } });
    expect(overview(summarizeCategories(template, facts, readiness), [candidate()], readiness)).toEqual({
      verified: 1, review: 1, suggestions: 1, notAdded: 4, needed: 2,
    });
  });

  it("searches names and values without caring about case or Turkish accents", () => {
    const hits = searchKnowledge("AYLIK", facts, template, null, "tr");
    expect(hits.map((h) => (h.kind === "fact" ? h.fact.key : h.item.identifier))).toEqual([
      "pricing.membership_monthly",
      "pricing.student_monthly",
    ]);
    expect(searchKnowledge("6.000", facts, template, null, "tr")).toHaveLength(1);
    // items not added yet are found by name too, so the owner can jump straight to adding them
    expect(searchKnowledge("single", facts, template, null, "en")).toEqual([{ kind: "item", item: expect.objectContaining({ identifier: "pricing.single_session" }) }]);
    expect(searchKnowledge("zumba", facts, template, null, "en")).toEqual([]);
    // the category name matches every fact in it
    const prices = searchKnowledge("prices", facts, template, null, "en", (c) => (c === "pricing" ? "Prices" : c));
    expect(prices.filter((h) => h.kind === "fact")).toHaveLength(2);
    expect(searchKnowledge("  ", facts, template, null, "tr")).toEqual([]);
  });
});

describe("slugFromLabel", () => {
  it.each([
    ["Reformer Pilates", "reformer_pilates"],
    ["Kişisel Antrenman", "kisisel_antrenman"],
    ["  İlk Seans — Ücretsiz!  ", "ilk_seans_ucretsiz"],
    ["ÇĞİÖŞÜ", "cgiosu"],
  ])("%s -> %s", (label, slug) => {
    expect(slugFromLabel(label)).toBe(slug);
  });
});
