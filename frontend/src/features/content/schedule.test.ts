import { describe, expect, it } from "vitest";
import {
  defaultSchedule,
  localToInstant,
  scheduleProblem,
  timezoneCity,
  toLocalFields,
} from "./schedule";

const ISTANBUL = "Europe/Istanbul";
const LISBON = "Europe/Lisbon";

describe("local time to instant (INV-19)", () => {
  it("19:00 in Istanbul (UTC+3) is 16:00 UTC", () => {
    expect(localToInstant("2026-10-21", "19:00", ISTANBUL)?.toISOString()).toBe("2026-10-21T16:00:00.000Z");
  });

  it("follows daylight saving: Lisbon is UTC+1 in summer and UTC+0 in winter", () => {
    expect(localToInstant("2026-07-01", "12:00", LISBON)?.toISOString()).toBe("2026-07-01T11:00:00.000Z");
    expect(localToInstant("2026-12-01", "12:00", LISBON)?.toISOString()).toBe("2026-12-01T12:00:00.000Z");
  });

  it("a time in the skipped hour does not exist (SCHEDULE_TIME_NONEXISTENT)", () => {
    // Lisbon, 29 March 2026: 01:00 jumps to 02:00.
    expect(localToInstant("2026-03-29", "01:30", LISBON)).toBeNull();
    expect(localToInstant("2026-03-29", "00:59", LISBON)?.toISOString()).toBe("2026-03-29T00:59:00.000Z");
    expect(localToInstant("2026-03-29", "02:00", LISBON)?.toISOString()).toBe("2026-03-29T01:00:00.000Z");
  });

  it("a time that exists twice is the earlier instant, like the server's", () => {
    // Lisbon, 25 October 2026: 02:00 goes back to 01:00, so 01:30 happens twice.
    expect(localToInstant("2026-10-25", "01:30", LISBON)?.toISOString()).toBe("2026-10-25T00:30:00.000Z");
  });

  it("malformed input is not an instant", () => {
    expect(localToInstant("", "19:00", ISTANBUL)).toBeNull();
    expect(localToInstant("2026-10-21", "7pm", ISTANBUL)).toBeNull();
  });

  it("round-trips to the fields of the date and time inputs", () => {
    const at = new Date("2026-10-21T16:00:00Z");
    expect(toLocalFields(at, ISTANBUL)).toEqual({ date: "2026-10-21", time: "19:00" });
  });
});

describe("what the server would say about a chosen time", () => {
  const NOW = new Date("2026-10-21T10:00:00Z"); // 13:00 in Istanbul

  it("accepts a time far enough ahead", () => {
    expect(scheduleProblem("2026-10-21", "19:00", ISTANBUL, NOW, true)).toBeNull();
  });

  it("staff (waiting for approval) need at least 15 minutes", () => {
    expect(scheduleProblem("2026-10-21", "13:10", ISTANBUL, NOW, true)).toBe("SCHEDULE_TOO_SOON_FOR_APPROVAL");
    expect(scheduleProblem("2026-10-21", "13:15", ISTANBUL, NOW, true)).toBeNull();
    // Someone who approves themselves can pick a close time.
    expect(scheduleProblem("2026-10-21", "13:10", ISTANBUL, NOW, false)).toBeNull();
  });

  it("the past is refused, with a minute of grace", () => {
    expect(scheduleProblem("2026-10-21", "12:00", ISTANBUL, NOW, false)).toBe("SCHEDULE_IN_PAST");
    expect(scheduleProblem("2026-10-21", "12:59", ISTANBUL, NOW, false)).toBeNull();
  });

  it("names a time in a clock gap", () => {
    const now = new Date("2026-03-20T10:00:00Z");
    expect(scheduleProblem("2026-03-29", "01:30", LISBON, now, false)).toBe("SCHEDULE_TIME_NONEXISTENT");
  });

  it("says nothing about a field that is not filled in yet", () => {
    expect(scheduleProblem("", "19:00", ISTANBUL, NOW, true)).toBeNull();
  });
});

describe("defaults and labels", () => {
  it("suggests a time an hour ahead, rounded up to five minutes, on the workspace clock", () => {
    const now = new Date("2026-10-21T10:02:00Z"); // 13:02 in Istanbul
    expect(defaultSchedule(now, ISTANBUL)).toEqual({ date: "2026-10-21", time: "14:05" });
  });

  it("takes the city out of the zone id", () => {
    expect(timezoneCity("Europe/Istanbul")).toBe("Istanbul");
    expect(timezoneCity("America/New_York")).toBe("New York");
  });
});
