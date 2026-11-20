import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { setLanguage } from "@/i18n";

afterEach(() => vi.unstubAllGlobals());
const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const DATA = { enabled: false, hours: 6, text: { tr: "", en: "" }, default_text: { tr: "Yardımcı olabilir miyiz?", en: "Can we help further?" }, min_hours: 1, max_hours: 20 };

function setup(role: "owner" | "manager" | "staff" = "owner", put?: (request: RecordedRequest) => Response) {
  mockApi({
    "GET /api/v1/meta": () => json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json({ ...ME, memberships: ME.memberships.map(item => item.workspace_id === WS_GOLKENT ? { ...item, role } : item) }),
    "GET /api/v1/auth/sessions": () => json([]),
    [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/members`]: () => json({ items: [] }),
    [`GET ${BASE}/deletion-status`]: () => json({ is_deleting: false }),
    [`GET ${BASE}/follow-up-settings`]: () => json(DATA),
    [`PUT ${BASE}/follow-up-settings`]: put ?? (() => json(DATA)),
  });
  renderApp(`/w/${WS_GOLKENT}/more/settings`);
}

describe("follow-up settings", () => {
  it("defaults off and saves the exact owner form", async () => {
    let saved: unknown;
    setup("owner", request => { saved = request.body; return json({ ...DATA, ...(request.body as object) }); });
    const user = userEvent.setup();
    const toggle = await screen.findByRole("checkbox", { name: "Müşteri sessiz kaldığında takip mesajı hazırla" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await user.selectOptions(screen.getByLabelText("Bekleme süresi (saat)"), "8");
    const panel = screen.getByRole("region", { name: "Müşteri takip mesajı" });
    await user.click(within(panel).getByRole("button", { name: "Değişiklikleri kaydet" }));
    await waitFor(() => expect(saved).toEqual({ enabled: true, hours: 8, text: { tr: "", en: "" } }));
  });

  it.each(["manager", "staff"] as const)("shows read-only controls for %s", async role => {
    setup(role);
    expect(await screen.findByRole("checkbox", { name: "Müşteri sessiz kaldığında takip mesajı hazırla" })).toBeDisabled();
    const panel = screen.getByRole("region", { name: "Müşteri takip mesajı" });
    expect(within(panel).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows server template validation", async () => {
    setup("owner", () => problem(422, "VALIDATION_FAILED", { errors: [{ field: "text.tr", code: "LITERAL_VALUE", params: {} }] }));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Özel metin (Türkçe)"), "500 TL");
    const panel = screen.getByRole("region", { name: "Müşteri takip mesajı" });
    await user.click(within(panel).getByRole("button", { name: "Değişiklikleri kaydet" }));
    expect(await screen.findByText("Fiyat, saat, iletişim ve bağlantılar için bilgi yer tutucuları kullanın.")).toBeInTheDocument();
  });

  it("renders English and Turkish strings", async () => {
    setup();
    expect(await screen.findByText("Müşteri takip mesajı")).toBeInTheDocument();
    await setLanguage("en");
    expect(await screen.findByText("Customer follow-up")).toBeInTheDocument();
    expect(screen.getByLabelText("Wait this many hours")).toBeInTheDocument();
  });
});
