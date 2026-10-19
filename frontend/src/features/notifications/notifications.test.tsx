import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BASE, approval, notification } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

function routes(extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

const changed = notification();
const requested = notification({
  id: "n0000000-0000-4000-8000-000000000002",
  type: "approval.requested",
  params: { action: "command.update_fact", summary: { label: "Aylık üyelik" } },
});
const unreadList = { items: [changed, requested], unread_count: 2, next_cursor: null };

describe("notification bell", () => {
  it("shows the unread count and describes each notification in plain language", async () => {
    mockApi(routes({ [`GET ${BASE}/notifications`]: () => json(unreadList) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("notification-count")).toHaveTextContent("2");

    await userEvent.setup().click(screen.getByRole("button", { name: /Bildirimler, 2 okunmamış bildirim/ }));
    const sheet = await screen.findByRole("dialog", { name: "Bildirimler" });
    expect(within(sheet).getByText("Aylık üyelik değişti: 6.000 ₺ / ay → 7.000 ₺ / ay")).toBeInTheDocument();
    expect(within(sheet).getByText("Onayınız bekleniyor: Aylık üyelik")).toBeInTheDocument();
  });

  it("marks everything read", async () => {
    let read = false;
    const requests = mockApi(
      routes({
        [`GET ${BASE}/notifications`]: () =>
          json(read ? { items: [], unread_count: 0, next_cursor: null } : unreadList),
        [`POST ${BASE}/notifications/read-all`]: () => {
          read = true;
          return noContent();
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bildirimler/ }));
    await user.click(await screen.findByRole("button", { name: "Tümünü okundu say" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/read-all"))).toBe(true));
    await waitFor(() => expect(screen.queryByTestId("notification-count")).toBeNull());
    expect(requests.find((r) => r.path.endsWith("/read-all"))!.headers.get("X-CSRF-Token")).toBe(
      "csrf-token-for-tests",
    );
  });

  it("shows an empty state and no badge when nothing is new", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}`);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Bildirimler" }));
    expect(await screen.findByText("Yeni bildirim yok")).toBeInTheDocument();
    expect(screen.queryByTestId("notification-count")).toBeNull();
  });

  it("opening an approval notification marks it read and goes to the approvals screen", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/notifications`]: () => json({ ...unreadList, items: [requested], unread_count: 1 }),
        [`POST ${BASE}/notifications/${requested.id}/read`]: () => json(requested),
        [`GET ${BASE}/approvals`]: () => json({ items: [approval()], next_cursor: null }),
      }),
    );
    const { router } = renderApp(`/w/${WS_GOLKENT}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bildirimler/ }));
    await user.click(await screen.findByRole("link", { name: "Aç" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${WS_GOLKENT}/approvals`));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/read"))).toBe(true));
  });
});
