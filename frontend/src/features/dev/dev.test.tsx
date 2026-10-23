import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BASE } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const DEV = `/api/v1/dev/workspaces/${WS_GOLKENT}`;

function routes(published: unknown[], extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    "GET /api/v1/dev/scripts": () => json([]),
    [`GET ${DEV}/failure-rules`]: () => json({ items: [], next_cursor: null }),
    "GET /api/v1/dev/jobs": () => json({ items: [], next_cursor: null }),
    [`GET ${DEV}/simulator/published`]: () => json({ items: published, next_cursor: null }),
    ...extra,
  };
}

describe("dev panel: simulator", () => {
  it("lists what was published to the fake Instagram, each marked as simulated", async () => {
    mockApi(
      routes([
        {
          media_id: "sim_media_1",
          container_id: "sim_container_1",
          media_type: "STORIES",
          caption: null,
          permalink: "https://instagram.example/sim/sim_media_1",
          published_at: "2026-10-20T16:00:05Z",
          is_simulated: true,
        },
        {
          media_id: "sim_media_2",
          container_id: "sim_container_2",
          media_type: "IMAGE",
          caption: "Aylık üyelik şimdi çok uygun!",
          permalink: "https://instagram.example/sim/sim_media_2",
          published_at: "2026-10-20T17:00:00Z",
          is_simulated: true,
        },
      ]),
    );
    renderApp(`/w/${WS_GOLKENT}/more/dev`);
    const card = await screen.findByTestId("sim-published");
    const rows = await within(card).findAllByTestId("sim-published-item");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("STORIES");
    expect(rows[0]).toHaveTextContent("(açıklamasız)");
    expect(rows[0]).toHaveTextContent("sim_media_1");
    expect(within(rows[0]!).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("Aylık üyelik şimdi çok uygun!");
  });

  it("says when nothing has been published yet, and can refresh", async () => {
    const requests = mockApi(routes([]));
    renderApp(`/w/${WS_GOLKENT}/more/dev`);
    const card = await screen.findByTestId("sim-published");
    expect(await within(card).findByText("Simülatörde henüz yayınlanmış gönderi yok.")).toBeInTheDocument();
    const before = requests.filter((r) => r.path.endsWith("/simulator/published")).length;
    await userEvent.setup().click(within(card).getByRole("button", { name: "Yenile" }));
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.path.endsWith("/simulator/published")).length).toBeGreaterThan(before),
    );
  });

  it("offers the publish operations in the failure rules", async () => {
    mockApi(routes([]));
    renderApp(`/w/${WS_GOLKENT}/more/dev`);
    const select = await screen.findByLabelText("İşlem");
    const options = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(expect.arrayContaining(["create_container", "container_status", "publish"]));
  });
});

describe("dev panel: demo reset", () => {
  const NEW_WS = "0b6f5f6e-3d4c-4f0f-9a47-6f3a3c1e8a11";

  it("asks for confirmation, resets, and opens the workspace with the new id", async () => {
    const requests = mockApi(
      routes([], {
        [`POST ${DEV}/reset`]: () => json({ workspace_id: NEW_WS }),
        [`GET /api/v1/workspaces/${NEW_WS}`]: () => json(workspace(NEW_WS)),
      }),
    );
    const { router } = renderApp(`/w/${WS_GOLKENT}/more/dev`);
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("dev-reset"));
    const dialog = await screen.findByRole("dialog", { name: "Demo sıfırlansın mı?" });
    expect(requests.some((r) => r.path.endsWith("/reset"))).toBe(false); // nothing before the confirmation

    await user.click(within(dialog).getByTestId("dev-reset-confirm"));

    await vi.waitFor(() => expect(router.state.location.pathname).toBe(`/w/${NEW_WS}`));
    expect(requests.filter((r) => r.method === "POST" && r.path === `${DEV}/reset`)).toHaveLength(1);
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const requests = mockApi(routes([]));
    renderApp(`/w/${WS_GOLKENT}/more/dev`);
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("dev-reset"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Vazgeç" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith("/reset"))).toBe(false);
  });
});
