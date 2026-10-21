import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DailyReport } from "@/api/types";
import { BASE } from "@/test/aiFixtures";
import { contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi, type RecordedRequest } from "@/test/mockApi";
import { REPORT_BASE, metric, report } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const DAY = "2026-10-15";

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m)),
};

type Handler = (request: RecordedRequest) => Response;

function routes(extra: Record<string, Handler> = {}, me = ME, llmMode = "fake") {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: llmMode, supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

const accounts = (...items: ReturnType<typeof socialAccount>[]) => ({
  [`GET ${BASE}/social-accounts`]: () => json({ items, next_cursor: null }),
});

const reportWith = (metrics: ReturnType<typeof metric>[], overrides: Partial<DailyReport> = {}) =>
  ({ [`GET ${REPORT_BASE}`]: () => json(report(DAY, { metrics, ...overrides })) });

const FULL_METRICS = [
  metric("inbound_messages", 12, "messages", DAY),
  metric("replies_sent", 5, "messages", DAY),
  metric("attention_now", 2, "messages", DAY),
  metric("pending_approvals_now", 3, "approvals", DAY),
  metric("content_published", 1, "content", DAY),
  metric("content_failed", 1, "content", DAY),
  metric("content_on_hold_now", 4, "content", DAY),
  metric("integration_errors", 0, "problems", DAY),
];

describe("Home: attention cards", () => {
  it("counts what waits for the owner, from the live report, and links to the right screen", async () => {
    mockApi(routes({ ...reportWith(FULL_METRICS), ...accounts(socialAccount()) }));
    renderApp(`/w/${WS_GOLKENT}`);

    const approvals = await screen.findByTestId("attention-pending_approvals_now");
    expect(within(approvals).getByText("Onay bekleyen")).toBeInTheDocument();
    expect(within(approvals).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/approvals`);
    expect(within(approvals).getByRole("link")).toHaveTextContent("3");

    const human = screen.getByTestId("attention-attention_now");
    expect(within(human).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/inbox`);
    expect(human).toHaveTextContent("2");

    const failures = screen.getByTestId("attention-content_failed");
    expect(within(failures).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/content?tab=problems`);
    expect(failures).toHaveTextContent("1");

    const hold = screen.getByTestId("attention-content_on_hold_now");
    expect(within(hold).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/content?tab=problems`);
    expect(hold).toHaveTextContent("4");
    expect(screen.queryByTestId("attention-none")).toBeNull();
  });

  it("says so when nothing waits (empty state)", async () => {
    mockApi(
      routes({
        ...reportWith([
          metric("attention_now", 0, "messages", DAY),
          metric("pending_approvals_now", 0, "approvals", DAY),
          metric("content_failed", 0, "content", DAY),
          metric("content_on_hold_now", 0, "content", DAY),
        ]),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("attention-none")).toHaveTextContent("Şu an sizi bekleyen bir şey yok.");
    expect(screen.queryByTestId("attention-pending_approvals_now")).toBeNull();
  });

  it("the on-hold card opens the problems tab, which lists the held posts", async () => {
    const held = contentItem({ id: "c5000000-0000-4000-8000-0000000000a1", status: "on_hold", title: "Bekleyen post" });
    const requests = mockApi(
      routes({
        ...reportWith(FULL_METRICS),
        [`GET ${BASE}/content-items`]: (request) =>
          json({ items: request.search.includes("tab=problems") ? [held] : [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await userEvent.setup().click(within(await screen.findByTestId("attention-content_on_hold_now")).getByRole("link"));
    expect(await screen.findByRole("heading", { name: "İçerik", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Bekleyen post")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sorunlar" })).toHaveAttribute("aria-selected", "true");
    expect(requests.some((r) => r.path.endsWith("/content-items") && r.search.includes("tab=problems"))).toBe(true);
  });

  it("the report's old on-hold shortcut (?status=on_hold) lands on the problems tab too", async () => {
    const requests = mockApi(routes({ [`GET ${BASE}/content-items`]: () => json({ items: [], next_cursor: null }) }));
    renderApp(`/w/${WS_GOLKENT}/content?status=on_hold`);
    expect(await screen.findByRole("tab", { name: "Sorunlar" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith("/content-items") && r.search.includes("tab=problems"))).toBe(true),
    );
  });
});

describe("Home: banners and status strip", () => {
  it("shows the red reauth banner with the renew link, driven by the account status", async () => {
    mockApi(routes({ ...reportWith([]), ...accounts(socialAccount({ status: "needs_reauth" })) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const banner = await screen.findByTestId("banner-needs-reauth");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(
      "Instagram bağlantınız yenilenmeli. Yenilenene kadar yanıt gönderilemez ve gönderiler yayınlanamaz.",
    );
    expect(within(banner).getByRole("link", { name: "Bağlantıyı yenile" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/automation`,
    );
    expect(screen.queryByTestId("banner-degraded")).toBeNull();
    expect(screen.getByTestId("home-connection")).toHaveTextContent("yeniden bağlanmalı");
  });

  it("shows the amber degraded banner without an action", async () => {
    mockApi(routes({ ...reportWith([]), ...accounts(socialAccount({ status: "degraded" })) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const banner = await screen.findByTestId("banner-degraded");
    expect(banner).toHaveTextContent("Instagram'a şu an ulaşılamıyor, otomatik olarak tekrar denenecek.");
    expect(within(banner).queryByRole("link")).toBeNull();
    expect(screen.queryByTestId("banner-needs-reauth")).toBeNull();
  });

  it("shows no banner while the account is connected", async () => {
    mockApi(routes({ ...reportWith([]), ...accounts(socialAccount()) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("home-connection")).toHaveTextContent("bağlı");
    expect(screen.queryByTestId("banner-needs-reauth")).toBeNull();
    expect(screen.queryByTestId("banner-degraded")).toBeNull();
  });

  it("only the owner is offered the renew link (a manager is told who can)", async () => {
    mockApi(
      routes({
        [`GET /api/v1/workspaces/${WS_HARBOR}`]: () => json(workspace(WS_HARBOR)),
        [`GET /api/v1/workspaces/${WS_HARBOR}/readiness`]: () => json(READINESS),
        [`GET /api/v1/workspaces/${WS_HARBOR}/social-accounts`]: () =>
          json({ items: [socialAccount({ status: "needs_reauth" })], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_HARBOR}`);
    const banner = await screen.findByTestId("banner-needs-reauth");
    expect(within(banner).queryByRole("link")).toBeNull();
    expect(banner).toHaveTextContent("Bunu yalnızca sahip değiştirebilir.");
  });

  it("shows the connection, the simulation badge and the AI mode", async () => {
    mockApi(routes({ ...accounts(socialAccount()) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("home-connection")).toHaveTextContent("Instagram @golkent.fitness: bağlı");
    expect(await screen.findByTestId("home-ai-mode")).toHaveTextContent("Çevrimdışı demo yapay zekâsı");
    expect(screen.getAllByTestId("simulated-badge").length).toBeGreaterThan(0);
  });

  it("says so when no account is connected, and names a live AI", async () => {
    mockApi(routes({}, ME, "openai"));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("home-connection")).toHaveTextContent("Bağlı hesap yok");
    expect(await screen.findByTestId("home-ai-mode")).toHaveTextContent("Yapay zekâ açık");
  });
});

describe("Home: upcoming posts and failures", () => {
  it("lists the next three scheduled posts on the workspace clock", async () => {
    const scheduled = [1, 2, 3].map((n) =>
      contentItem({
        id: `c5000000-0000-4000-8000-00000000010${n}`,
        status: "scheduled",
        title: `Gönderi ${n}`,
        scheduled_at: `2026-10-16T1${n}:00:00Z`,
      }),
    );
    const requests = mockApi(
      routes({
        ...reportWith([]),
        [`GET ${BASE}/content-items`]: (request) =>
          json({ items: request.search.includes("tab=scheduled") ? scheduled : [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const card = (await screen.findByText("Gönderi 1")).closest("section, div[aria-labelledby]") as HTMLElement;
    expect(within(card).getAllByRole("listitem")).toHaveLength(3);
    expect(within(card).getByRole("link", { name: "Gönderi 1" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${scheduled[0]!.id}`,
    );
    expect(card).toHaveTextContent("14:00"); // 11:00 UTC in Istanbul
    expect(within(card).getAllByTestId("simulated-badge")).toHaveLength(3);
    expect(requests.some((r) => r.search.includes("tab=scheduled") && r.search.includes("limit=3"))).toBe(true);
  });

  it("has an empty state for the upcoming posts", async () => {
    mockApi(routes({ ...reportWith([]) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("upcoming-empty")).toHaveTextContent("Planlanmış gönderi yok.");
  });

  it("lists the three most recent failures with what happened", async () => {
    const failed = [
      contentItem({ id: "c5000000-0000-4000-8000-0000000002a1", status: "failed", title: "Hikaye A", last_error_code: "MEDIA_REJECTED" }),
      contentItem({ id: "c5000000-0000-4000-8000-0000000002a2", status: "failed", title: "Hikaye B", last_error_code: null }),
    ];
    const requests = mockApi(
      routes({
        ...reportWith([]),
        [`GET ${BASE}/content-items`]: (request) =>
          json({ items: request.search.includes("status=failed") ? failed : [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const link = await screen.findByRole("link", { name: "Hikaye A" });
    expect(link).toHaveAttribute("href", `/w/${WS_GOLKENT}/content/${failed[0]!.id}`);
    expect(screen.getByRole("link", { name: "Hikaye B" })).toBeInTheDocument();
    expect(screen.getByText("Yayınlanırken bir şeyler ters gitti.")).toBeInTheDocument(); // unknown code
    expect(requests.some((r) => r.search.includes("status=failed") && r.search.includes("limit=3"))).toBe(true);
    expect(screen.queryByTestId("failures-empty")).toBeNull();
  });

  it("has an empty state for failures", async () => {
    mockApi(routes({ ...reportWith([]) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("failures-empty")).toHaveTextContent("Başarısız olan bir gönderi yok.");
  });
});

describe("Home: today's numbers", () => {
  it("shows the day's numbers as links to their records, the partial time and the badge", async () => {
    mockApi(
      routes({
        ...reportWith(FULL_METRICS, {
          is_partial: true,
          period_end: `${DAY}T11:35:00Z`,
          has_simulated_data: true,
        }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const inbound = await screen.findByTestId("number-inbound_messages");
    expect(within(inbound).getByRole("link")).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports/${DAY}/inbound_messages`,
    );
    expect(inbound).toHaveTextContent("12");
    expect(screen.getByTestId("number-replies_sent")).toHaveTextContent("5");
    expect(screen.getByTestId("number-content_published")).toHaveTextContent("1");
    expect(screen.getByText("14:35 itibarıyla")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Günlük raporu aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports`,
    );
  });

  it("has an empty state for a quiet day", async () => {
    mockApi(
      routes({
        ...reportWith([], { summary: { empty: true, text: "", sections: [] } }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("numbers-empty")).toHaveTextContent("Bugün henüz bir şey olmadı.");
  });
});

describe("Home: staff", () => {
  it("shows inbox numbers only: no approvals, failures or on-hold cards, no content numbers", async () => {
    mockApi(
      routes(
        {
          ...reportWith([
            metric("inbound_messages", 7, "messages", DAY),
            metric("replies_sent", 2, "messages", DAY),
            metric("attention_now", 1, "messages", DAY),
          ]),
        },
        STAFF_ME,
      ),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("attention-attention_now")).toHaveTextContent("1");
    expect(screen.queryByTestId("attention-pending_approvals_now")).toBeNull();
    expect(screen.queryByTestId("attention-content_failed")).toBeNull();
    expect(screen.queryByTestId("attention-content_on_hold_now")).toBeNull();
    expect(await screen.findByTestId("number-inbound_messages")).toHaveTextContent("7");
    expect(screen.getByTestId("number-replies_sent")).toHaveTextContent("2");
    expect(screen.queryByTestId("number-content_published")).toBeNull();
    expect(screen.queryByTestId("number-integration_errors")).toBeNull();
  });
});
