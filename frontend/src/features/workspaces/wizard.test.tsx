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
    "GET /api/v1/meta": () => json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
  };

  it("walks name, category and market, creates the workspace, then lets the owner skip trying the assistant", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...base,
      "POST /api/v1/workspaces": () => json(created, 201),
      [`GET /api/v1/workspaces/${created.id}/knowledge/imports/website/prefill`]: () => json({ url: null }),
      [`GET /api/v1/workspaces/${created.id}`]: () => json(created),
      [`GET /api/v1/workspaces/${created.id}/facts`]: () => json({ items: [], next_cursor: null }),
      [`GET /api/v1/workspaces/${created.id}/facts/template`]: () => json([]),
      [`GET /api/v1/workspaces/${created.id}/readiness`]: () => json({ level: "not_ready", requirements: [] }),
      [`GET /api/v1/workspaces/${created.id}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
      [`GET /api/v1/workspaces/${created.id}/assistant/test-chat`]: () => json({ items: [], remaining_this_hour: 20, remaining_today: 60 }),
    });
    const { router } = renderApp("/workspaces/new");

    const name = await screen.findByLabelText("İşletme adı");
    expect(screen.getByRole("button", { name: "Devam" })).toBeDisabled(); // a name is required
    await user.type(name, "  Lale Pilates ");
    await user.click(screen.getByRole("button", { name: "Devam" }));

    await user.click(screen.getByRole("radio", { name: "Spor salonu, pilates ve yoga" }));
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

    // The last step runs after creation and is skippable: nothing navigates until the owner chooses.
    expect(await screen.findByRole("heading", { name: "Asistanınızı deneyin" })).toBeVisible();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Deneme");
    expect(await screen.findByTestId("suggestions")).toBeVisible();
    expect(router.state.location.pathname).toBe("/workspaces/new");
    await user.click(screen.getByRole("button", { name: "Şimdilik geç" }));
    expect(await screen.findByRole("heading", { name: "İçe aktar" })).toBeVisible();
    expect(screen.getByTestId("website-import-url")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Şimdilik geç" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${created.id}/more/knowledge`));
    const post = requests.find((r) => r.method === "POST");
    expect(post?.body).toEqual({
      name: "Lale Pilates",
      business_category: "fitness",
      market: "tr",
      default_locale: "tr",
      timezone: "Europe/Istanbul",
      currency: "TRY",
    });
    expect(post?.headers.get("x-csrf-token")).toBe("csrf-token-for-tests");
  });

  it("lets the owner try the assistant right after creation and then continue to business details", async () => {
    const user = userEvent.setup();
    let sent = false;
    const chatPath = `/api/v1/workspaces/${created.id}/assistant/test-chat`;
    const turn = { id: "70000000-0000-4000-8000-000000000001", status: "pending", customer_text: "Saat kaçta açıksınız?", created_at: "2026-11-15T09:00:00Z", completed_at: null, draft: null, is_simulated: true };
    const requests = mockApi({
      ...base,
      "POST /api/v1/workspaces": () => json(created, 201),
      [`GET /api/v1/workspaces/${created.id}/knowledge/imports/website/prefill`]: () => json({ url: null }),
      [`GET /api/v1/workspaces/${created.id}`]: () => json(created),
      [`GET /api/v1/workspaces/${created.id}/facts`]: () => json({ items: [], next_cursor: null }),
      [`GET /api/v1/workspaces/${created.id}/facts/template`]: () => json([]),
      [`GET /api/v1/workspaces/${created.id}/readiness`]: () => json({ level: "not_ready", requirements: [] }),
      [`GET /api/v1/workspaces/${created.id}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
      [`GET ${chatPath}`]: () => json({ items: sent ? [turn] : [], remaining_this_hour: 19, remaining_today: 59 }),
      [`POST ${chatPath}/messages`]: () => { sent = true; return json(turn, 202); },
    });
    const { router } = renderApp("/workspaces/new");
    await user.type(await screen.findByLabelText("İşletme adı"), "Lale Pilates");
    await user.click(screen.getByRole("button", { name: "Devam" }));
    await user.click(screen.getByRole("radio", { name: "Spor salonu, pilates ve yoga" }));
    await user.click(screen.getByRole("button", { name: "Devam" }));
    await user.click(screen.getByRole("button", { name: "Çalışma alanı oluştur" }));

    expect(await screen.findByText(/İşletme bilgilerinizi henüz eklemediniz/)).toBeVisible();
    await user.click(await screen.findByRole("button", { name: "Saat kaçta açıksınız?" }));
    expect(await screen.findByText("Asistanınız yazıyor…")).toBeVisible();
    expect(screen.getAllByTestId("simulated-badge")[0]).toBeVisible();
    expect(requests.find((r) => r.path === `${chatPath}/messages`)?.body).toEqual({ text: "Saat kaçta açıksınız?" });
    expect(router.state.location.pathname).toBe("/workspaces/new");
    await user.click(screen.getByRole("button", { name: "İşletme bilgilerine devam et" }));
    expect(await screen.findByRole("heading", { name: "İçe aktar" })).toBeVisible();
    expect(screen.getByTestId("website-import-url")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Şimdilik geç" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${created.id}/more/knowledge`));
  });

  it("is offered from the workspace picker", async () => {
    const user = userEvent.setup();
    mockApi(base);
    renderApp("/");
    await user.click(await screen.findByRole("link", { name: /Çalışma alanı oluştur/ }));
    expect(await screen.findByLabelText("İşletme adı")).toBeInTheDocument();
  });
});
