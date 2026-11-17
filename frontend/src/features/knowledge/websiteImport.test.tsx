import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Extraction } from "@/api/types";
import { Providers } from "@/app/providers";
import { createQueryClient } from "@/app/queryClient";
import { BASE } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, candidate, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { candidatesKey } from "./hooks";
import { WebsiteImportForm } from "./WebsiteImportForm";

afterEach(() => vi.unstubAllGlobals());
const RUN = "b0000000-0000-4000-8000-000000000001";
const PATH = `/w/${WS_GOLKENT}/more/knowledge`;
const PREFILL = `GET ${BASE}/knowledge/imports/website/prefill`;
const POST = `POST ${BASE}/knowledge/imports/website`;
const POLL = `GET ${BASE}/knowledge/extractions/${RUN}`;
const run = (overrides: Partial<Extraction> = {}): Extraction => ({
  run_id: RUN, status: "queued", candidates_created: 0, error_code: null, injection_suspected: false, ...overrides,
});
function routes(extra: Record<string, () => Response | Promise<Response>> = {}) {
  return {
    "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${BASE}/facts/template`]: () => json([]),
    [`GET ${BASE}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
    [PREFILL]: () => json({ url: null }),
    ...extra,
  };
}
async function submit(url = "https://example.com") {
  const user = userEvent.setup();
  await user.type(await screen.findByTestId("website-import-url"), url);
  await user.click(screen.getByTestId("website-import-submit"));
}

describe("website import", () => {
  it("posts the URL and request ID, polls, invalidates candidates/readiness and never writes facts", async () => {
    let polls = 0;
    const requests = mockApi(routes({
      [POST]: () => json(run(), 202),
      [POLL]: () => json(polls++ === 0 ? run({ status: "running" }) : run({ status: "succeeded", candidates_created: 2 })),
    }));
    const { client } = renderApp(PATH);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await submit();
    expect(await screen.findByText("Web siteniz okunuyor…")).toBeVisible();
    expect(await screen.findByText("2 öneri bulundu. İncelemenizi bekliyor.", undefined, { timeout: 4000 })).toBeVisible();
    expect(requests.find((request) => request.method === "POST")?.body).toEqual({ client_request_id: expect.any(String), url: "https://example.com" });
    expect(polls).toBeGreaterThan(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["readiness", WS_GOLKENT] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: candidatesKey(WS_GOLKENT, "pending") });
    await waitFor(() => {
      expect(requests.filter((r) => r.path === `${BASE}/fact-candidates`).length).toBeGreaterThan(1);
      expect(requests.filter((r) => r.path === `${BASE}/readiness`).length).toBeGreaterThan(1);
    });
    expect(screen.getByRole("link", { name: "Önerileri incele" })).toHaveAttribute("href", `${PATH}/suggestions`);
    expect(requests.some((r) => r.method !== "GET" && r.path.includes("/facts"))).toBe(false);
  }, 15_000);

  it("prefills the field", async () => {
    mockApi(routes({ [PREFILL]: () => json({ url: "https://prefilled.example" }) }));
    renderApp(PATH);
    await waitFor(() => expect(screen.getByTestId("website-import-url")).toHaveValue("https://prefilled.example"));
  });

  it("does not overwrite typing when prefill arrives late", async () => {
    let resolve!: (response: Response) => void;
    mockApi(routes({ [PREFILL]: () => new Promise<Response>((done) => { resolve = done; }) }));
    const { client } = renderApp(PATH);
    await userEvent.setup().type(await screen.findByTestId("website-import-url"), "https://typed.example");
    resolve(json({ url: "https://prefilled.example" }));
    await waitFor(() => expect(client.getQueryData(["website-import-prefill", WS_GOLKENT])).toEqual({ url: "https://prefilled.example" }));
    await waitFor(() => expect(screen.getByTestId("website-import-url")).toHaveValue("https://typed.example"));
    expect(screen.queryByDisplayValue("https://prefilled.example")).not.toBeInTheDocument();
  });

  it("blocks empty submission and shows both controls on Knowledge", async () => {
    const requests = mockApi(routes());
    renderApp(PATH);
    const button = await screen.findByTestId("website-import-submit");
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Devam etmek için web sitesi adresinizi girin.");
    expect(screen.getByTestId("open-instagram-import")).toBeVisible();
    await userEvent.setup().click(button);
    expect(requests.some((r) => r.method === "POST")).toBe(false);
    expect(screen.queryByRole("link", { name: "Önerileri incele" })).not.toBeInTheDocument();
  });

  it("associates a 422 URL error with the field and clears it when edited", async () => {
    mockApi(routes({ [POST]: () => problem(422, "VALIDATION_FAILED", { errors: [{ field: "url", code: "invalid_url" }] }) }));
    renderApp(PATH);
    await submit("www.example.com");
    const input = screen.getByTestId("website-import-url");
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(input).toHaveAccessibleDescription("Adresi kontrol edin: http:// veya https:// ile başlayan, herkese açık bir web sitesi olmalıdır.");
    await userEvent.setup().type(input, "/about");
    expect(input).not.toHaveAttribute("aria-invalid", "true");
  });

  it("shows a failed run's catalog explanation and next action", async () => {
    mockApi(routes({ [POST]: () => json(run(), 202), [POLL]: () => json(run({ status: "failed", error_code: "WEBSITE_BLOCKED" })) }));
    renderApp(PATH);
    await submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Bu web sitesi adresi engellendi.");
    expect(alert).toHaveTextContent("Standart HTTP veya HTTPS bağlantı noktası kullanan herkese açık bir işletme sitesi girin.");
    expect(screen.queryByRole("link", { name: "Önerileri incele" })).not.toBeInTheDocument();
  });

  it("shows no-result and injection messages without a review link", async () => {
    mockApi(routes({ [POST]: () => json(run(), 202), [POLL]: () => json(run({ status: "succeeded", injection_suspected: true })) }));
    renderApp(PATH);
    await submit();
    expect(await screen.findByText("Web sitenizde önerilecek yeni bir bilgi bulunamadı.")).toBeVisible();
    expect(screen.getByText("Web sitenizde talimat gibi görünen bazı bölümler vardı; bunlar yok sayıldı.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Önerileri incele" })).not.toBeInTheDocument();
  });

  it("works without current-workspace context and notifies once per completed run", async () => {
    let polls = 0;
    mockApi(routes({ [POST]: () => json(run(), 202), [POLL]: () => {
      polls++;
      return json(run({ status: "succeeded", candidates_created: 1 }));
    } }));
    const client = createQueryClient();
    const onDone = vi.fn();
    render(<Providers client={client}><WebsiteImportForm workspaceId={WS_GOLKENT} onDone={onDone} /></Providers>);
    await submit();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    await client.invalidateQueries({ queryKey: ["extraction", WS_GOLKENT, RUN] });
    await waitFor(() => expect(polls).toBe(2));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe("website candidate sources", () => {
  it.each(["https://example.com/prices", "http://example.com/contact", "javascript:alert(1)", "invalid", null])("labels the source and only links public web protocols: %s", async (url) => {
    mockApi(routes({ [`GET ${BASE}/fact-candidates`]: () => json({ items: [candidate({ source_type: "website", source: {
      origin: "website_page", posted_at: null, url, age_days: null, stale: true, simulated: true,
    } })], next_cursor: null }) }));
    renderApp(`${PATH}/suggestions`);
    expect(await screen.findByText("Web sitenizden")).toBeVisible();
    expect(screen.getByText("Simülasyon")).toBeVisible();
    expect(screen.queryByText(/Fiyatlar değişmiş olabilir/)).not.toBeInTheDocument();
    if (url?.startsWith("http")) {
      expect(screen.getByText("example.com")).toBeVisible();
      const link = screen.getByRole("link", { name: "Sayfayı gör" });
      expect(link).toHaveAttribute("href", url);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link.getAttribute("rel")).toContain("noopener");
    } else {
      expect(screen.queryByRole("link", { name: "Sayfayı gör" })).not.toBeInTheDocument();
    }
  });
});
