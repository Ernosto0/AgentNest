import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { contentItem } from "@/test/contentFixtures";
import {
  buildWeek,
  coverageOf,
  earlierThan,
  friendlyMoment,
  groupByDay,
  parseWeekParam,
  weekStartOf,
} from "./agenda";

const TZ = "Europe/Istanbul"; // UTC+3, no DST
// Wednesday 11 November 2026, 10:00 in Istanbul.
const NOW = new Date("2026-11-11T07:00:00Z");

const at = (id: string, scheduled_at: string | null) => contentItem({ id, status: "scheduled", scheduled_at });

describe("agenda weeks (INV-19)", () => {
  it("starts weeks on Monday", () => {
    expect(weekStartOf("2026-11-11")).toBe("2026-11-09"); // Wednesday
    expect(weekStartOf("2026-11-09")).toBe("2026-11-09"); // Monday
    expect(weekStartOf("2026-11-15")).toBe("2026-11-09"); // Sunday
  });

  it("normalises a week address to its Monday and ignores anything that is not a date", () => {
    expect(parseWeekParam("2026-11-13")).toBe("2026-11-09");
    expect(parseWeekParam("next")).toBeNull();
    expect(parseWeekParam("2026-13-45")).toBeNull();
    expect(parseWeekParam(null)).toBeNull();
  });

  it("places items on their workspace-local day, not their UTC day", () => {
    // 22:30 UTC on the 11th is 01:30 on the 12th in Istanbul.
    const late = at("late", "2026-11-11T22:30:00Z");
    const days = buildWeek([late], "2026-11-09", TZ, { capped: false, lastDay: null }, NOW);
    expect(days.map((d) => d.day)).toEqual([
      "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15",
    ]);
    expect(days.find((d) => d.day === "2026-11-12")?.items.map((i) => i.id)).toEqual(["late"]);
    expect(days.find((d) => d.isToday)?.day).toBe("2026-11-11");
    expect(days.filter((d) => d.isPast).map((d) => d.day)).toEqual(["2026-11-09", "2026-11-10"]);
  });

  it("orders a day's items by time", () => {
    const days = buildWeek(
      [at("b", "2026-11-12T15:00:00Z"), at("a", "2026-11-12T06:00:00Z")],
      "2026-11-09",
      TZ,
      { capped: false, lastDay: null },
      NOW,
    );
    expect(days[3]?.items.map((i) => i.id)).toEqual(["a", "b"]);
  });

  it("marks days after a full page as not loaded instead of free", () => {
    const items = [at("a", "2026-11-10T08:00:00Z"), at("b", "2026-11-12T08:00:00Z")];
    const coverage = coverageOf(items, 2, TZ);
    expect(coverage).toEqual({ capped: true, lastDay: "2026-11-12" });
    const days = buildWeek(items, "2026-11-09", TZ, coverage, NOW);
    expect(days.filter((d) => d.notLoaded).map((d) => d.day)).toEqual(["2026-11-13", "2026-11-14", "2026-11-15"]);
    // A page that is not full covers everything.
    expect(coverageOf(items, 50, TZ)).toEqual({ capped: false, lastDay: null });
  });

  it("keeps items the board cannot place: earlier than the week, or with no time", () => {
    const items = [at("old", "2026-11-01T08:00:00Z"), at("none", null), at("now", "2026-11-11T08:00:00Z")];
    expect(earlierThan(items, "2026-11-09", TZ).map((i) => i.id)).toEqual(["old", "none"]);
  });

  it("groups every item by local day for the list, with untimed items last", () => {
    const groups = groupByDay([at("x", null), at("b", "2026-11-12T08:00:00Z"), at("a", "2026-11-10T08:00:00Z")], TZ);
    expect(groups.map((g) => [g.day, g.items.map((i) => i.id)])).toEqual([
      ["2026-11-10", ["a"]],
      ["2026-11-12", ["b"]],
      [null, ["x"]],
    ]);
  });
});

describe("friendly moments", () => {
  const t = i18n.getFixedT("tr");
  it("says today, tomorrow and yesterday on the workspace clock", () => {
    expect(friendlyMoment("2026-11-11T16:00:00Z", TZ, "tr", t, {}, NOW)).toBe("Bugün · 19:00");
    expect(friendlyMoment("2026-11-12T06:30:00Z", TZ, "tr", t, {}, NOW)).toBe("Yarın · 09:30");
    expect(friendlyMoment("2026-11-10T06:30:00Z", TZ, "tr", t, { withTime: false }, NOW)).toBe("Dün");
  });

  it("adds the year only for another year", () => {
    expect(friendlyMoment("2026-11-20T09:00:00Z", TZ, "tr", t, { withTime: false }, NOW)).not.toMatch(/2026/);
    expect(friendlyMoment("2027-01-05T09:00:00Z", TZ, "tr", t, { withTime: false }, NOW)).toMatch(/2027/);
  });
});
