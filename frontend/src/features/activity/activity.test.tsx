import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { ACTIVITY_PATH, entry } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

/** The nth element, failing loudly when the list is shorter than the test expects. */
function nth<T>(list: T[], index: number): T {
  const found = list[index];
  if (found === undefined) throw new Error(`expected at least ${index + 1} elements`);
  return found;
}

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m)),
};

function routes(extra: Record<string, () => Response> = {}, me = ME) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

const page = (items: ReturnType<typeof entry>[], next_cursor: string | null = null) => ({ items, next_cursor });

describe("activity feed", () => {
  it("lists the entries with actor, time on the workspace clock and a link to the resource", async () => {
    mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () =>
          json(
            page([
              entry(1, { is_simulated: true }),
              entry(2, {
                action: "fact.updated",
                group: "knowledge",
                text: "Bilgi güncellendi",
                actor: { type: "user", label: "Eski üye" },
                occurred_at: "2026-10-15T20:30:00Z",
                resource: { type: "business_fact", id: "f0000000-0000-4000-8000-000000000001", label: "Aylık üyelik", link: null },
              }),
            ]),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);

    const rows = await screen.findAllByTestId("activity-entry");
    expect(rows).toHaveLength(2);
    expect(within(nth(rows, 0)).getByText("Yanıt gönderildi")).toBeInTheDocument();
    expect(within(nth(rows, 0)).getByRole("link", { name: "ayse_k" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/inbox/c1000000-0000-4000-8000-000000000001`,
    );
    expect(within(nth(rows, 0)).getByText(/Demo Sahip · /)).toBeInTheDocument();
    // 20:30 UTC is 23:30 in Istanbul, the workspace clock.
    expect(within(nth(rows, 1)).getByText(/Eski üye · .*23:30/)).toBeInTheDocument();
    // No screen for the fact: its label is plain text, not a link.
    expect(within(nth(rows, 1)).queryByRole("link")).toBeNull();
    expect(within(nth(rows, 1)).getByText("Aylık üyelik")).toBeInTheDocument();
    // Only the simulated entry carries the badge (INV-09).
    expect(within(nth(rows, 0)).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(nth(rows, 1)).queryByTestId("simulated-badge")).toBeNull();
  });

  it("asks for the chosen group and shows its entries", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(
            last.search.includes("type=messages")
              ? page([entry(3, { action: "message.received", group: "messages", text: "Mesaj alındı" })])
              : page([entry(1), entry(2)]),
          );
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    expect(await screen.findAllByTestId("activity-entry")).toHaveLength(2);
    const chip = screen.getByRole("button", { name: "Mesajlar" });
    expect(chip).toHaveAttribute("aria-pressed", "false");

    await userEvent.setup().click(chip);
    expect(await screen.findByText("Mesaj alındı")).toBeInTheDocument();
    expect(screen.getAllByTestId("activity-entry")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Mesajlar" })).toHaveAttribute("aria-pressed", "true");
    expect(requests.some((r) => r.path === ACTIVITY_PATH && r.search.includes("type=messages"))).toBe(true);
  });

  it("loads the next page with the cursor and then stops offering more", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(last.search.includes("cursor=abc") ? page([entry(2)]) : page([entry(1)], "abc"));
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    expect(await screen.findAllByTestId("activity-entry")).toHaveLength(1);

    await userEvent.setup().click(screen.getByRole("button", { name: "Daha fazla yükle" }));
    await waitFor(() => expect(screen.getAllByTestId("activity-entry")).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "Daha fazla yükle" })).toBeNull();
  });

  it("explains an empty feed", async () => {
    mockApi(routes({ [`GET ${ACTIVITY_PATH}`]: () => json(page([])) }));
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    expect(await screen.findByText("Henüz etkinlik yok")).toBeInTheDocument();
  });

  it("is in the More menu for the owner and not for staff", async () => {
    mockApi(routes());
    const owner = renderApp(`/w/${WS_GOLKENT}/more`);
    expect(await screen.findByRole("link", { name: /Etkinlik/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/activity`,
    );
    expect(screen.getByRole("link", { name: /Günlük rapor/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports`,
    );
    owner.unmount();

    vi.unstubAllGlobals();
    mockApi(routes({}, STAFF_ME));
    renderApp(`/w/${WS_GOLKENT}/more`);
    expect(await screen.findByRole("link", { name: /Günlük rapor/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Etkinlik/ })).toBeNull();
  });
});
