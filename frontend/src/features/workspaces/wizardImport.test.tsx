import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());
const created = workspace(WS_GOLKENT, { id: "44444444-4444-4444-8444-444444444444" });
const BASE = `/api/v1/workspaces/${created.id}`;
const RUN = "b0000000-0000-4000-8000-000000000001";
const POST = `POST ${BASE}/knowledge/imports/website`;
function routes(extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () => json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    "POST /api/v1/workspaces": () => json(created, 201),
    [`GET ${BASE}`]: () => json(created),
    [`GET ${BASE}/knowledge/imports/website/prefill`]: () => json({ url: null }),
    [`GET ${BASE}/assistant/test-chat`]: () => json({ items: [], remaining_this_hour: 20, remaining_today: 60 }),
    [`GET ${BASE}/facts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${BASE}/facts/template`]: () => json([]),
    [`GET ${BASE}/readiness`]: () => json({ level: "not_ready", requirements: [] }),
    [`GET ${BASE}/fact-candidates`]: () => json({ items: [], next_cursor: null }),
    ...extra,
  };
}
async function reachImport() {
  const view = renderApp("/workspaces/new");
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("İşletme adı"), "Lale Pilates");
  await user.click(screen.getByRole("button", { name: "Devam" }));
  await user.click(screen.getByRole("radio", { name: "Spor salonu, pilates ve yoga" }));
  await user.click(screen.getByRole("button", { name: "Devam" }));
  await user.click(screen.getByRole("button", { name: "Çalışma alanı oluştur" }));
  await user.click(await screen.findByRole("button", { name: "Şimdilik geç" }));
  const heading = await screen.findByRole("heading", { name: "İçe aktar" });
  expect(heading).toHaveFocus();
  expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("5. İçe aktar");
  expect(screen.queryByTestId("open-instagram-import")).not.toBeInTheDocument();
  return { ...view, user };
}

describe("wizard import step", () => {
  it("allows an empty prefill and skips to Knowledge without importing", async () => {
    const requests = mockApi(routes());
    const { user, router } = await reachImport();
    expect(screen.getByTestId("website-import-url")).toHaveValue("");
    expect(screen.getByTestId("website-import-submit")).toBeDisabled();
    expect(screen.getByText(/Instagram: Daha sonra/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Şimdilik geç" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${created.id}/more/knowledge`));
    expect(requests.some((request) => request.method === "POST" && request.path.includes("/knowledge/"))).toBe(false);
  });

  it("imports for the newly created workspace and offers review navigation", async () => {
    const requests = mockApi(routes({
      [POST]: () => json({ run_id: RUN, status: "queued", candidates_created: 0, error_code: null, injection_suspected: false }, 202),
      [`GET ${BASE}/knowledge/extractions/${RUN}`]: () => json({ run_id: RUN, status: "succeeded", candidates_created: 1, error_code: null, injection_suspected: false }),
    }));
    const { user, router } = await reachImport();
    await user.type(screen.getByTestId("website-import-url"), "https://example.com");
    await user.click(screen.getByTestId("website-import-submit"));
    const review = await screen.findByRole("button", { name: "Önerileri incele" });
    expect(screen.getByRole("link", { name: "Önerileri incele" })).toHaveAttribute("href", `/w/${created.id}/more/knowledge/suggestions`);
    expect(requests.find((request) => `${request.method} ${request.path}` === POST)?.body).toEqual({ client_request_id: expect.any(String), url: "https://example.com" });
    expect(requests.some((r) => r.method !== "GET" && r.path.includes("/facts"))).toBe(false);
    await user.click(review);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${created.id}/more/knowledge/suggestions`));
  });

  it("shows URL validation inside the wizard and keeps skipping available", async () => {
    mockApi(routes({ [POST]: () => problem(422, "VALIDATION_FAILED", { errors: [{ field: "url", code: "invalid_url" }] }) }));
    const { user } = await reachImport();
    const input = screen.getByTestId("website-import-url");
    await user.type(input, "https://localhost");
    await user.click(screen.getByTestId("website-import-submit"));
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(input).toHaveAccessibleDescription("Adresi kontrol edin: http:// veya https:// ile başlayan, herkese açık bir web sitesi olmalıdır.");
    expect(screen.getByRole("button", { name: "Şimdilik geç" })).toBeEnabled();
  });
});
