import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Extraction } from "@/api/types";
import { BASE } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, candidate, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());
const RUN = "a0000000-0000-4000-8000-000000000001";
const PATH = `/w/${WS_GOLKENT}/more/knowledge`;
const run = (overrides: Partial<Extraction> = {}): Extraction => ({
  run_id: RUN, status: "queued", candidates_created: 0, error_code: null, injection_suspected: false, ...overrides,
});
function routes(extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${BASE}/facts/template`]: () => json([]),
    [`GET ${BASE}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
    [`GET ${BASE}/social-accounts`]: () => json({ items: [{ id: "ig", status: "connected", platform: "instagram", username: "business", capabilities: {}, is_simulated: false }], next_cursor: null }),
    ...extra,
  };
}
async function clickImport() {
  const button = await screen.findByTestId("open-instagram-import");
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.setup().click(button);
}

describe("Instagram import", () => {
  it("posts a request ID, polls and refreshes pending suggestions and readiness", async () => {
    let polls = 0;
    const requests = mockApi(routes({
      [`POST ${BASE}/knowledge/imports/instagram`]: () => json(run(), 202),
      [`GET ${BASE}/knowledge/extractions/${RUN}`]: () => json(polls++ === 0 ? run({ status: "running" }) : run({ status: "succeeded", candidates_created: 2 })),
    }));
    renderApp(PATH);
    await clickImport();
    expect(await screen.findByText("Instagram profiliniz ve son gönderileriniz inceleniyor…")).toBeInTheDocument();
    expect(await screen.findByText("2 öneri bulundu. Sizi bekliyor.", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ client_request_id: expect.any(String) });
    await waitFor(() => {
      expect(requests.filter((r) => r.path === `${BASE}/fact-candidates`).length).toBeGreaterThan(1);
      expect(requests.filter((r) => r.path === `${BASE}/readiness`).length).toBeGreaterThan(1);
    });
    expect(polls).toBeGreaterThan(1);
    expect(requests.some((r) => r.method !== "GET" && r.path.includes("/facts"))).toBe(false);
  }, 15_000);

  it("shows the failed run and catalog error", async () => {
    mockApi(routes({
      [`POST ${BASE}/knowledge/imports/instagram`]: () => json(run(), 202),
      [`GET ${BASE}/knowledge/extractions/${RUN}`]: () => json(run({ status: "failed", error_code: "PROVIDER_UNAVAILABLE" })),
    }));
    renderApp(PATH);
    await clickImport();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Instagram'dan bilgiler alınamadı.");
    expect(alert.querySelectorAll("p")).toHaveLength(2);
    expect(alert.querySelectorAll("p")[1]?.textContent).toBeTruthy();
  });

  it.each([{ items: [] }, { items: [{ status: "needs_reauth" }] }])("disables the button with a hint for unusable accounts: %j", async ({ items }) => {
    const requests = mockApi(routes({ [`GET ${BASE}/social-accounts`]: () => json({ items }) }));
    renderApp(PATH);
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/social-accounts"))).toBe(true));
    const button = await screen.findByTestId("open-instagram-import");
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Önce Instagram'ı bağlayın");
    await userEvent.setup().click(button);
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("shows a server conflict if the account becomes unavailable", async () => {
    mockApi(routes({ [`POST ${BASE}/knowledge/imports/instagram`]: () => problem(409, "CONFLICT_STATE", { params: { reason: "no_connected_account" } }) }));
    renderApp(PATH);
    await clickImport();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("explains an empty result and ignored instructions, including for degraded accounts", async () => {
    mockApi(routes({
      [`GET ${BASE}/social-accounts`]: () => json({ items: [{ status: "degraded" }] }),
      [`POST ${BASE}/knowledge/imports/instagram`]: () => json(run(), 202),
      [`GET ${BASE}/knowledge/extractions/${RUN}`]: () => json(run({ status: "succeeded", injection_suspected: true })),
    }));
    renderApp(PATH);
    await clickImport();
    expect(await screen.findByText("Profilinizde ve son gönderilerinizde önerilecek yeni bir bilgi bulunamadı.")).toBeInTheDocument();
    expect(screen.getByText("Profilinizde talimat gibi görünen bazı bölümler vardı; bunlar yok sayıldı.")).toBeInTheDocument();
  });
});

describe("Instagram candidate sources", () => {
  const source = (overrides: Partial<NonNullable<ReturnType<typeof candidate>["source"]>> = {}) => ({
    origin: "caption", posted_at: "2026-04-30T12:00:00Z", age_days: 200, stale: true, simulated: false, url: "https://www.instagram.com/p/example/", ...overrides,
  });
  function show(value: ReturnType<typeof candidate>["source"]) {
    mockApi(routes({ [`GET ${BASE}/fact-candidates`]: () => json({ items: [candidate({ source_type: "instagram_profile", source: value })], next_cursor: null }) }));
    renderApp(`${PATH}/suggestions`);
    return screen.findByTestId("candidate-pricing.membership_monthly");
  }
  it("labels a bio", async () => {
    await show(source({ origin: "bio", posted_at: null, stale: false, age_days: null, url: null }));
    expect(screen.getByText("Instagram biyografinizden")).toBeInTheDocument();
  });
  it("dates an old caption and warns about prices with a safe post link", async () => {
    await show(source());
    const date = new Intl.DateTimeFormat("tr", { dateStyle: "medium", timeZone: "Europe/Istanbul" }).format(new Date("2026-04-30T12:00:00Z"));
    expect(screen.getByText(`${date} tarihli bir gönderiden`)).toBeInTheDocument();
    expect(screen.getByText(/Bu gönderi 200 gün önce paylaşılmış/)).toHaveTextContent("Fiyatlar değişmiş olabilir");
    const link = screen.getByRole("link", { name: "Gönderiyi gör" });
    expect(link).toHaveAttribute("href", "https://www.instagram.com/p/example/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
  it("does not warn for fresh captions and labels simulated data", async () => {
    await show(source({ age_days: 2, stale: false, simulated: true }));
    expect(screen.queryByText(/Fiyatlar değişmiş olabilir/)).not.toBeInTheDocument();
    expect(screen.getByText("Simülasyon")).toBeInTheDocument();
  });
  it("handles missing dates and refuses non-https post links", async () => {
    await show(source({ posted_at: null, stale: false, url: "javascript:alert(1)" }));
    expect(screen.getByText("Bir gönderiden")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Gönderiyi gör" })).not.toBeInTheDocument();
  });
  it("keeps the original review controls for null sources", async () => {
    const card = await show(null);
    expect(card).toHaveTextContent("5.500 ₺ / ay");
    expect(screen.getByRole("button", { name: "Mevcut değeri koru" })).toBeInTheDocument();
    expect(screen.queryByText("Instagram biyografinizden")).not.toBeInTheDocument();
  });
  it("ignores unknown origins while retaining the simulation label", async () => {
    await show(source({ origin: "website", simulated: true }));
    expect(screen.queryByRole("link", { name: "Gönderiyi gör" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Fiyatlar değişmiş olabilir/)).not.toBeInTheDocument();
    expect(screen.getByText("Simülasyon")).toBeInTheDocument();
  });
});
