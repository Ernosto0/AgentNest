import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { defaultsForMarket, timezoneOptions } from "./wizardDefaults";

afterEach(() => vi.unstubAllGlobals());

describe("market defaults", () => {
  it("follow the market, not the UI language", () => {
    expect(defaultsForMarket("tr", "Europe/Lisbon")).toEqual({
      default_locale: "tr",
      timezone: "Europe/Istanbul",
      currency: "TRY",
    });
    expect(defaultsForMarket("global", "Europe/Lisbon")).toEqual({
      default_locale: "en",
      timezone: "Europe/Lisbon",
      currency: "EUR",
    });
    expect(defaultsForMarket("global", "").timezone).toBe("UTC");
  });

  it("always offers the selected time zone", () => {
    expect(timezoneOptions("Nowhere/Fictional")).toContain("Nowhere/Fictional");
    expect(timezoneOptions("Europe/Istanbul")).toContain("Europe/Istanbul");
  });
});

describe("workspace wizard", () => {
  const created = workspace(WS_GOLKENT, { id: "44444444-4444-4444-8444-444444444444", name: "Lale Pilates" });
  const base = {
    "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
  };

  it("walks name, category and market, then creates the workspace and lands on the checklist", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...base,
      "POST /api/v1/workspaces": () => json(created, 201),
      [`GET /api/v1/workspaces/${created.id}`]: () => json(created),
      [`GET /api/v1/workspaces/${created.id}/facts`]: () => json({ items: [], next_cursor: null }),
      [`GET /api/v1/workspaces/${created.id}/facts/template`]: () => json([]),
      [`GET /api/v1/workspaces/${created.id}/readiness`]: () => json({ level: "not_ready", requirements: [] }),
      [`GET /api/v1/workspaces/${created.id}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
    });
    const { router } = renderApp("/workspaces/new");

    const name = await screen.findByLabelText("İşletme adı");
    expect(screen.getByRole("button", { name: "Devam" })).toBeDisabled(); // a name is required
    await user.type(name, "  Lale Pilates ");
    await user.click(screen.getByRole("button", { name: "Devam" }));

    await user.click(screen.getByRole("radio", { name: "Pilates stüdyosu" }));
    await user.click(screen.getByRole("button", { name: "Devam" }));

    // Türkiye defaults
    expect(screen.getByLabelText("Saat dilimi")).toHaveValue("Europe/Istanbul");
    expect(screen.getByLabelText("Para birimi")).toHaveValue("TRY");
    expect(screen.getByLabelText("İşletme dili")).toHaveValue("tr");

    // switching the market re-applies its defaults
    await user.selectOptions(screen.getByLabelText("Pazar"), "global");
    expect(screen.getByLabelText("Para birimi")).toHaveValue("EUR");
    expect(screen.getByLabelText("İşletme dili")).toHaveValue("en");
    await user.selectOptions(screen.getByLabelText("Pazar"), "tr");

    await user.click(screen.getByRole("button", { name: "Çalışma alanı oluştur" }));

    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${created.id}/more/knowledge`));
    const post = requests.find((r) => r.method === "POST");
    expect(post?.body).toEqual({
      name: "Lale Pilates",
      business_category: "pilates_studio",
      market: "tr",
      default_locale: "tr",
      timezone: "Europe/Istanbul",
      currency: "TRY",
    });
    expect(post?.headers.get("x-csrf-token")).toBe("csrf-token-for-tests");
  });

  it("is offered from the workspace picker", async () => {
    const user = userEvent.setup();
    mockApi(base);
    renderApp("/");
    await user.click(await screen.findByRole("link", { name: /Çalışma alanı oluştur/ }));
    expect(await screen.findByLabelText("İşletme adı")).toBeInTheDocument();
  });
});
