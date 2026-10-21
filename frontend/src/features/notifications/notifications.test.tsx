import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { BASE, approval, notification } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import catalog from "./catalog.json";
import { describeNotification } from "./describe";

afterEach(() => vi.unstubAllGlobals());

function routes(extra: Record<string, (request: RecordedRequest) => Response> = {}) {
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
  it("shows the unread count and opens the notification centre", async () => {
    mockApi(routes({ [`GET ${BASE}/notifications`]: () => json(unreadList) }));
    const { router } = renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("notification-count")).toHaveTextContent("2");

    await userEvent.setup().click(screen.getByRole("link", { name: /Bildirimler, 2 okunmamış bildirim/ }));
    expect(router.state.location.pathname).toBe(`/w/${WS_GOLKENT}/more/notifications`);
    expect(await screen.findByRole("heading", { name: "Bildirimler", level: 1 })).toBeInTheDocument();
  });
});

describe("notification centre", () => {
  it("describes each notification in plain language, with the severity as an icon and a word", async () => {
    mockApi(routes({ [`GET ${BASE}/notifications`]: () => json(unreadList) }));
    renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    const list = await screen.findByRole("list", { name: "Bildirimler" });
    expect(within(list).getByText("Aylık üyelik değişti: 6.000 ₺ / ay → 7.000 ₺ / ay")).toBeInTheDocument();
    expect(within(list).getByText("Onayınız bekleniyor: Aylık üyelik")).toBeInTheDocument();
    const rows = list.querySelectorAll("[data-severity]");
    expect(rows[0]).toHaveAttribute("data-severity", "info");
    expect(within(rows[0] as HTMLElement).getByText("Bilgi")).toBeInTheDocument();
    expect(rows[0]!.querySelector("svg")).not.toBeNull();
  });

  it("names the severity of an urgent notification in words and shows the simulation badge", async () => {
    const reauth = notification({
      id: "n0000000-0000-4000-8000-000000000003",
      type: "account.needs_reauth",
      severity: "critical",
      params: { social_account_id: "a1", username: "golkent.demo" },
      is_simulated: true,
    });
    mockApi(
      routes({
        [`GET ${BASE}/notifications`]: () => json({ items: [reauth], unread_count: 1, next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    const row = (await screen.findByText("Instagram hesabınızı yeniden bağlayın")).closest(
      "[data-severity]",
    ) as HTMLElement;
    expect(row).toHaveAttribute("data-severity", "critical");
    expect(within(row).getByText("Acil")).toBeInTheDocument();
    expect(within(row).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/automation`,
    );
  });

  it("toggles between unread and all notifications", async () => {
    const read = notification({ read_at: "2026-10-15T12:10:00Z" });
    const requests = mockApi(
      routes({
        [`GET ${BASE}/notifications`]: (request) =>
          request.search.includes("unread=true")
            ? json({ items: [requested], unread_count: 1, next_cursor: null })
            : json({ items: [requested, read], unread_count: 1, next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    const user = userEvent.setup();
    expect(await screen.findByText("Onayınız bekleniyor: Aylık üyelik")).toBeInTheDocument();
    expect(screen.queryByText(/değişti: /)).toBeNull();
    expect(screen.getByRole("button", { name: "Okunmamış" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Tümü" }));
    expect(await screen.findByText(/değişti: /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tümü" })).toHaveAttribute("aria-pressed", "true");
    expect(requests.some((r) => r.search.includes("unread=true"))).toBe(true);
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
    renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Tümünü okundu say" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/read-all"))).toBe(true));
    await waitFor(() => expect(screen.queryByTestId("notification-count")).toBeNull());
    expect(requests.find((r) => r.path.endsWith("/read-all"))!.headers.get("X-CSRF-Token")).toBe(
      "csrf-token-for-tests",
    );
    expect(await screen.findByText("Yeni bildirim yok")).toBeInTheDocument();
  });

  it("shows an empty state and no badge when nothing is new", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    expect(await screen.findByText("Yeni bildirim yok")).toBeInTheDocument();
    expect(screen.queryByTestId("notification-count")).toBeNull();
    expect(screen.queryByRole("button", { name: "Tümünü okundu say" })).toBeNull();
  });

  it("opening an approval notification marks it read and goes to the approvals screen", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/notifications`]: () => json({ ...unreadList, items: [requested], unread_count: 1 }),
        [`POST ${BASE}/notifications/${requested.id}/read`]: () => json(requested),
        [`GET ${BASE}/approvals`]: () => json({ items: [approval()], next_cursor: null }),
      }),
    );
    const { router } = renderApp(`/w/${WS_GOLKENT}/more/notifications`);
    await userEvent.setup().click(await screen.findByRole("link", { name: "Aç" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${WS_GOLKENT}/approvals`));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/read"))).toBe(true));
  });
});

describe("the notification catalog", () => {
  it("has a sentence in describe.ts for every type (none falls back to the generic text)", () => {
    const t = i18n.getFixedT("tr");
    const generic = t("notifications.type.unknown");
    expect(catalog.types.length).toBeGreaterThan(0);
    for (const { type, severity } of catalog.types) {
      const text = describeNotification(
        t,
        notification({ type, severity, params: { title: "Yaz", reason: "FACT_CHANGED", capability: "messaging" } }),
        "tr",
      );
      expect(text, type).not.toBe(generic);
      expect(text, type).not.toBe("");
      expect(["info", "attention", "critical"]).toContain(severity);
    }
  });

  it("describes the types the report and the connection work add", () => {
    const t = i18n.getFixedT("tr");
    expect(
      describeNotification(t, notification({ type: "report.daily_ready", params: { local_date: "2026-10-14" } }), "tr"),
    ).toBe("2026-10-14 günlük raporu hazır");
    expect(
      describeNotification(
        t,
        notification({ type: "account.permission_missing", params: { capability: "publish_story_image" } }),
        "tr",
      ),
    ).toBe("Instagram izni eksik: hikâye yayınlama");
  });
});
