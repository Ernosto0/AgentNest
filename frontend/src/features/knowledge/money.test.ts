/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { formatMoneyAmount, parseMoneyInput, parsePhone, type MoneyLocale } from "./money";

interface Case {
  locale: MoneyLocale;
  text: string;
  currency: string;
  money?: [string, string];
  ambiguous?: [string, string][];
  error?: string;
}

// The same file the backend tests run: the two parsers must agree on every vector.
// (vitest runs from frontend/, so the shared folder is one level up.)
const CASES: Case[] = JSON.parse(
  readFileSync(resolve(process.cwd(), "..", "shared", "money-cases.json"), "utf8"),
);

describe("parseMoneyInput (shared vectors)", () => {
  it("has the same coverage as the backend", () => {
    expect(CASES.length).toBeGreaterThanOrEqual(30);
  });

  it.each(CASES.map((c) => [`${c.locale}: ${JSON.stringify(c.text)}`, c] as const))("%s", (_name, c) => {
    const result = parseMoneyInput(c.text, c.locale, c.currency);
    if (c.error) {
      expect(result).toEqual({ kind: "error", code: c.error });
    } else if (c.ambiguous) {
      expect(result.kind).toBe("ambiguous");
      if (result.kind === "ambiguous") {
        expect(result.alternatives.map((m) => [m.amount, m.currency])).toEqual(c.ambiguous);
      }
    } else {
      expect(result.kind).toBe("money");
      if (result.kind === "money") {
        expect([result.money.amount, result.money.currency]).toEqual(c.money);
      }
    }
  });
});

describe("formatMoneyAmount", () => {
  it.each([
    ["6000.00", "TRY", "tr", "6.000 ₺"],
    ["7000.50", "TRY", "tr", "7.000,50 ₺"],
    ["1200.00", "EUR", "en", "€1,200"],
    ["6000.00", "TRY", "en", "TRY 6,000"],
    ["50.00", "USD", "en", "$50"],
  ] as const)("%s %s in %s is %s", (amount, currency, locale, expected) => {
    expect(formatMoneyAmount(amount, currency, locale).replace(/\s/g, " ")).toBe(expected);
  });
});

describe("parsePhone", () => {
  it.each([
    ["0555 000 00 00", "+905550000000"],
    ["+90 555 000 00 00", "+905550000000"],
    ["555 000 00 00", "+905550000000"],
    ["+44 20 7946 0958", "+442079460958"],
  ])("%s", (text, expected) => {
    expect(parsePhone(text)).toBe(expected);
  });

  it.each(["", "abc", "123", "0155 000 00 00"])("rejects %j", (text) => {
    expect(parsePhone(text)).toBeNull();
  });
});
