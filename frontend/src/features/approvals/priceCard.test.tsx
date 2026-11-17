import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { describeResult } from "@/features/commands/messages";
import { PriceCardSummary } from "./PriceCardSummary";

const SUMMARY = { label: "Aylık üyelik", key: "pricing.membership_monthly", price_formatted: "6.000 ₺ / ay", format: "story", template: "price_card" };

afterEach(async () => {
  await i18n.changeLanguage("tr");
});

describe("make a price card confirmation", () => {
  it("shows the verified price and says only a draft is made (TR)", () => {
    render(<PriceCardSummary summary={SUMMARY} />);
    expect(screen.getByTestId("price-card-summary")).toHaveTextContent("Aylık üyelik");
    expect(screen.getByTestId("price-card-summary")).toHaveTextContent("6.000 ₺ / ay");
    expect(screen.getByTestId("price-card-summary")).toHaveTextContent("Story (9:16)");
    expect(screen.getByText(/Hiçbir şey onaylanmaz, zamanlanmaz veya yayınlanmaz/)).toBeInTheDocument();
  });

  it("says the same in English", async () => {
    await i18n.changeLanguage("en");
    render(<PriceCardSummary summary={{ ...SUMMARY, format: "feed" }} />);
    expect(screen.getByTestId("price-card-summary")).toHaveTextContent("Post (4:5)");
    expect(screen.getByText(/Nothing is approved, scheduled or published/)).toBeInTheDocument();
  });

  it("has result messages in both languages", async () => {
    const t = i18n.t.bind(i18n);
    expect(describeResult(t, "command.price_card_started", { title: "Fiyat kartı: Aylık üyelik" })).toContain("Fiyat kartı: Aylık üyelik");
    expect(describeResult(t, "command.price_card_not_a_price", { label: "Telefon" })).toContain("Telefon");
    await i18n.changeLanguage("en");
    const en = i18n.t.bind(i18n);
    expect(describeResult(en, "command.price_card_started", { title: "Price card: Monthly" })).toContain("Price card: Monthly");
    expect(describeResult(en, "command.price_card_no_price", {})).toContain("verified price");
    expect(describeResult(en, "command.price_card_fact_unusable", { label: "Day pass" })).toContain("Day pass");
  });
});
