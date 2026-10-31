import { describe, expect, it } from "vitest";
import { returnDestination } from "./returnTo";

describe("returnDestination", () => {
  it("defaults to root when from is missing or empty", () => {
    expect(returnDestination()).toBe("/");
    expect(returnDestination({})).toBe("/");
    expect(returnDestination({ pathname: "" })).toBe("/");
  });

  it("rejects non-relative or unsafe paths", () => {
    expect(returnDestination({ pathname: "https://evil.com" })).toBe("/");
    expect(returnDestination({ pathname: "//evil.com" })).toBe("/");
    expect(returnDestination({ pathname: "/path\\with\\backslash" })).toBe("/");
  });

  it("prevents login loop", () => {
    expect(returnDestination({ pathname: "/login" })).toBe("/");
  });

  it("preserves valid pathnames with query parameters and hash", () => {
    expect(returnDestination({ pathname: "/w/123/inbox" })).toBe("/w/123/inbox");
    expect(
      returnDestination({ pathname: "/w/123/inbox", search: "?filter=needs_human" }),
    ).toBe("/w/123/inbox?filter=needs_human");
    expect(
      returnDestination({ pathname: "/invite/tok-abc", hash: "#section" }),
    ).toBe("/invite/tok-abc#section");
    expect(
      returnDestination({
        pathname: "/w/123/approvals",
        search: "?tab=history",
        hash: "#item-1",
      }),
    ).toBe("/w/123/approvals?tab=history#item-1");
  });

  it("ignores search and hash if they lack leading markers", () => {
    expect(returnDestination({ pathname: "/w/123", search: "filter=needs_human" })).toBe("/w/123");
    expect(returnDestination({ pathname: "/w/123", hash: "anchor" })).toBe("/w/123");
  });
});

