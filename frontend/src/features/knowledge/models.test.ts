import { describe, expect, it } from "vitest";
import { fact, templateItem } from "@/test/fixtures";
import { buildHours, rowsFromValue } from "./editors/hoursModel";
import { slugFromLabel } from "./labels";
import { categoryEntries, summarize } from "./summary";

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

describe("category summary", () => {
  const template = [
    templateItem({ identifier: "a", key: "pricing.membership_monthly" }),
    templateItem({ identifier: "b", key: "pricing.student_monthly", status: "unverified" }),
    templateItem({ identifier: "c", key: "pricing.single_session", status: "missing" }),
    templateItem({
      identifier: "service.*", key: null, pattern: "service.*", category: "service",
      status: "missing", required_for: "ready", value_types: ["localized_text"],
    }),
    templateItem({
      identifier: "faq.*", key: null, pattern: "faq.*", category: "faq", status: "missing",
      value_types: ["localized_text"],
    }),
  ];
  const facts = [
    fact(),
    fact({ id: "2", key: "pricing.student_monthly", state: "unverified", status: "unverified" }),
    fact({ id: "3", key: "pricing.old", status: "archived", state: "archived" }),
  ];

  it("counts verified, needs-attention and missing per category, and always offers 'custom'", () => {
    const summaries = summarize(template, facts);
    expect(summaries.find((s) => s.category === "pricing")).toEqual({
      category: "pricing", verified: 1, attention: 1, missing: 1,
    });
    // a required pattern item with no fact counts as missing; an optional one does not
    expect(summaries.find((s) => s.category === "service")?.missing).toBe(1);
    expect(summaries.find((s) => s.category === "faq")?.missing).toBe(0);
    expect(summaries.at(-1)?.category).toBe("custom");
  });

  it("builds the entries of a category: fixed items, pattern items, leftovers and archived facts", () => {
    const withService = [
      ...facts,
      fact({ id: "4", key: "service.fitness", category: "service" }),
      fact({ id: "5", key: "custom.sauna", category: "custom" }),
    ];
    const pricing = categoryEntries("pricing", template, withService);
    expect(pricing.entries.map((e) => e.kind)).toEqual(["fixed", "fixed", "fixed"]);
    expect(pricing.archived.map((f) => f.key)).toEqual(["pricing.old"]);
    const service = categoryEntries("service", template, withService);
    expect(service.entries[0]).toMatchObject({ kind: "pattern", facts: [{ key: "service.fitness" }] });
    const custom = categoryEntries("custom", template, withService);
    expect(custom.entries).toEqual([{ kind: "other", facts: [expect.objectContaining({ key: "custom.sauna" })] }]);
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
