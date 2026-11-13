import { describe, expect, it } from "vitest";
import { entry } from "@/test/reportFixtures";
import { buildTimeline, worstLevel } from "./timeline";

const TZ = "Europe/Istanbul";
const at = (iso: string, n: number, key: string, level: "failure" | "warning" | "success" | "info" = "info") =>
  entry(n, { occurred_at: iso, collapse_key: key, level });

describe("buildTimeline", () => {
  it("splits days on the workspace clock and keeps every entry in order", () => {
    const entries = [
      at("2026-10-15T21:30:00Z", 1, "a"), // 16 Oct 00:30 in Istanbul
      at("2026-10-15T20:30:00Z", 2, "b"), // 15 Oct 23:30
      at("2026-10-14T08:00:00Z", 3, "c"),
    ];
    const days = buildTimeline(entries, TZ, false);
    expect(days.map((d) => [d.day, d.count])).toEqual([
      ["2026-10-16", 1],
      ["2026-10-15", 1],
      ["2026-10-14", 1],
    ]);
    const ids = days.flatMap((d) => d.items.flatMap((i) => (i.kind === "entry" ? [i.entry.id] : i.entries.map((e) => e.id))));
    expect(ids).toEqual(entries.map((e) => e.id));
  });

  it("gathers three or more entries of one key within a day at the newest one, keeping the rest in order", () => {
    const entries = [
      at("2026-10-15T12:00:00Z", 1, "x"),
      at("2026-10-15T11:00:00Z", 2, "y"),
      at("2026-10-15T10:00:00Z", 3, "x", "failure"),
      at("2026-10-15T09:00:00Z", 4, "z"),
      at("2026-10-15T08:00:00Z", 5, "x"),
      at("2026-10-15T07:00:00Z", 6, "y"),
    ];
    const [day] = buildTimeline(entries, TZ, false);
    const shape = day!.items.map((i) =>
      i.kind === "group" ? `group:${i.entries.map((e) => e.id.slice(-1)).join("")}:${i.level}` : i.entry.id.slice(-1),
    );
    // "y" appears only twice: those stay as rows in their own places.
    expect(shape).toEqual(["group:135:failure", "2", "4", "6"]);
    expect(day!.count).toBe(6);
  });

  it("never groups across a day boundary", () => {
    const entries = [
      at("2026-10-15T22:00:00Z", 1, "x"), // 16 Oct
      at("2026-10-15T20:00:00Z", 2, "x"), // 15 Oct
      at("2026-10-15T19:00:00Z", 3, "x"),
      at("2026-10-15T18:00:00Z", 4, "x"),
    ];
    const days = buildTimeline(entries, TZ, false);
    expect(days[0]!.items.map((i) => i.kind)).toEqual(["entry"]);
    expect(days[1]!.items.map((i) => i.kind)).toEqual(["group"]);
  });

  it("marks a group and a day that may continue on an unloaded page as open-ended", () => {
    const entries = [at("2026-10-15T12:00:00Z", 1, "a"), at("2026-10-15T11:00:00Z", 2, "x"), at("2026-10-15T10:00:00Z", 3, "x"), at("2026-10-15T09:00:00Z", 4, "x")];
    const [partial] = buildTimeline(entries, TZ, true);
    const group = partial!.items.find((i) => i.kind === "group");
    expect(group?.kind === "group" && group.openEnded).toBe(true);
    expect(partial!.openEnded).toBe(true);
    const [complete] = buildTimeline(entries, TZ, false);
    expect(complete!.openEnded).toBe(false);
  });

  it("takes the most serious level of a group", () => {
    expect(worstLevel([entry(1, { level: "success" }), entry(2, { level: "warning" }), entry(3, { level: "info" })])).toBe("warning");
    expect(worstLevel([])).toBe("info");
  });
});
