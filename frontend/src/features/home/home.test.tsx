import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DailyReport } from "@/api/types";
import { BASE } from "@/test/aiFixtures";
import { contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import tr from "@/i18n/locales/tr/common.json";
import { REPORT_BASE, metric, report } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const DAY = "2026-10-15";

const HEALTHY_AGENT = {
  state: "active", controller_mode: "agent", config_version: 3, controller_epoch: 2,
  is_simulated: true, session_counts: {}, pending_questions: 0, pending_approvals: 0, recent_actions: [],
};

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m)),
};

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

function routes(extra: Record<string, Handler> = {}, me = ME, llmMode = "fake") {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: llmMode, supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
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
    expect(approvals).toHaveTextContent("3");

    const human = screen.getByTestId("attention-attention_now");
    expect(within(human).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/inbox?attention=needs_human`);
    expect(human).toHaveTextContent("2");

    expect(screen.queryByTestId("attention-content_failed")).toBeNull(); // period metrics are not outstanding totals

    const hold = screen.getByTestId("attention-content_on_hold_now");
    expect(within(hold).getByRole("link")).toHaveAttribute("href", `/w/${WS_GOLKENT}/content?tab=problems`);
    expect(hold).toHaveTextContent("4");
    expect(screen.queryByTestId("attention-none")).toBeNull();
  });

  it("sums the outstanding items once every count is known", async () => {
    mockApi(routes({ ...reportWith(FULL_METRICS), [`GET ${BASE}/home/attention`]: () => json({ drafts: 1, unanswered_comments: 0 }) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const panel = await screen.findByTestId("home-attention");
    // approvals 3 + needs human 2 + on hold 4 + drafts 1; questions are 0 without accounts.
    expect(await within(panel).findByText("10 iş sizi bekliyor")).toBeInTheDocument();
    expect(within(panel).queryByTestId("attention-comments")).toBeNull();
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

describe("Home: banners", () => {
  it("updates failure banners and recovery while Home stays open", async () => {
    let account = socialAccount();
    mockApi(routes({ ...reportWith([]), [`GET ${BASE}/social-accounts`]: () => json({ items: [account] }) }));
    renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("home-attention")).toBeInTheDocument();

    account = socialAccount({ status: "needs_reauth" });
    expect(await screen.findByTestId("banner-needs-reauth", {}, { timeout: 6000 })).toBeInTheDocument();

    account = socialAccount({ status: "degraded" });
    expect(await screen.findByTestId("banner-degraded", {}, { timeout: 6000 })).toBeInTheDocument();
    expect(screen.queryByTestId("banner-needs-reauth")).toBeNull();

    account = socialAccount();
    await waitFor(() => expect(screen.queryByTestId("banner-degraded")).toBeNull(), {
      timeout: 6000,
    });
  }, 20_000);

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
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
    expect(screen.queryByTestId("banner-degraded")).toBeNull();
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
    expect(await screen.findByTestId("home-attention")).toBeInTheDocument();
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
});

describe("Home: upcoming content and failures", () => {
  it("previews the next scheduled items on the workspace clock, from one capped list", async () => {
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
    const list = await screen.findByTestId("upcoming-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getByRole("link", { name: /Gönderi 1/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${scheduled[0]!.id}`,
    );
    expect(list).toHaveTextContent("14:00"); // 11:00 UTC in Istanbul
    expect(within(list).getAllByTestId("simulated-badge")).toHaveLength(3);
    expect(within(list).getAllByText("Görsel yok")).toHaveLength(3); // placeholders say there is no image
    const card = screen.getByTestId("home-upcoming");
    expect(card).toHaveTextContent("Son kayıtların önizlemesi gösteriliyor."); // a preview, never a total
    expect(within(card).getByRole("link", { name: "Tüm içerik" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/content?tab=scheduled`);
    expect(requests.some((r) => r.search.includes("tab=scheduled") && r.search.includes("limit=50"))).toBe(true);
    expect(requests.some((r) => r.search.includes("tab=scheduled") && r.search.includes("limit=3"))).toBe(false);
  });

  it("has one empty state for upcoming content, with ways to create some", async () => {
    mockApi(routes({ ...reportWith([]), [`GET ${BASE}/content-items`]: () => json({ items: [], next_cursor: null }) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const empty = await screen.findByTestId("upcoming-empty");
    expect(empty).toHaveTextContent("Planlanmış içerik yok.");
    expect(within(empty).getByRole("button", { name: "Üret" })).toBeInTheDocument();
    expect(screen.getByTestId("week-summary")).toHaveTextContent("Gelecek 7 gün: 0 gönderi · 0 hikaye");
    await userEvent.setup().click(within(empty).getByRole("button", { name: "Hikaye hazırla" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
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
    await screen.findByText("Hikaye A");
    const link = screen.getAllByRole("link", { name: "Gönderiyi düzelt" })[0]!;
    expect(link).toHaveAttribute("href", `/w/${WS_GOLKENT}/content/${failed[0]!.id}`);
    expect(screen.getByText("Hikaye B")).toBeInTheDocument();
    expect(screen.getByText("Son kayıtların önizlemesi; toplam değil")).toBeInTheDocument();
    expect(requests.some((r) => r.search.includes("status=failed") && r.search.includes("limit=3"))).toBe(true);
    expect(screen.queryByTestId("failures-empty")).toBeNull();
  });

  it("has an empty state for failures", async () => {
    mockApi(routes({ ...reportWith([]) }));
    renderApp(`/w/${WS_GOLKENT}`);
    await screen.findByTestId("home-attention");
    expect(screen.queryByRole("link", { name: "Gönderiyi düzelt" })).toBeNull();
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

  it("keeps unchanged numbers quiet: no comparison line when today equals yesterday", async () => {
    const same = [metric("inbound_messages", 0, "messages", DAY), metric("replies_sent", 3, "messages", DAY)];
    const requests = mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(DAY, { is_partial: true, metrics: same })) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const strip = await screen.findByTestId("home-numbers");
    await waitFor(() => expect(requests.some((r) => r.search.includes("date="))).toBe(true));
    expect(within(strip).getByTestId("number-inbound_messages")).toHaveTextContent("0");
    expect(strip).not.toHaveTextContent("düne göre");
    expect(strip).not.toHaveTextContent("Aynı");
    expect(strip).not.toHaveTextContent("bugün şimdiye kadar vs. dünün tamamı"); // the note only explains shown comparisons
  });

  it("compares with yesterday without inventing a percentage from zero", async () => {
    const today = [metric("inbound_messages", 12, "messages", DAY), metric("replies_sent", 5, "messages", DAY), metric("integration_errors", 2, "problems", DAY)];
    const before = [metric("inbound_messages", 0, "messages", DAY), metric("replies_sent", 4, "messages", DAY), metric("integration_errors", 1, "problems", DAY)];
    mockApi(
      routes({
        [`GET ${REPORT_BASE}`]: (request) => json(report(DAY, { metrics: request.search.includes("date=") ? before : today })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const inbound = await screen.findByTestId("number-inbound_messages");
    await waitFor(() => expect(inbound).toHaveTextContent("Dün: 0"));
    expect(inbound).not.toHaveTextContent("%");
    expect(screen.getByTestId("number-replies_sent")).toHaveTextContent("+%25 düne göre");
    const errors = screen.getByTestId("number-integration_errors");
    expect(errors).toHaveTextContent("+%100 düne göre");
    expect(within(errors).getByText(/\+%100 düne göre/)).toHaveClass("text-danger"); // more errors is bad news
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

describe("Home: agent status card", () => {
  const account = socialAccount({ id: "a1000000-0000-4000-8000-000000000001", username: "studio_ist" });
  const agentUrl = `/api/v1/workspaces/${WS_GOLKENT}/accounts/${account.id}/agent`;

  it("renders assistant row with active state, mode and pause control for owner", async () => {
    const requests = mockApi(
      routes({
        ...reportWith([]),
        [`GET ${BASE}/social-accounts`]: () => json({ items: [account], next_cursor: null }),
        [`GET ${agentUrl}`]: () =>
          json({
            state: "active",
            controller_mode: "autonomous",
            config_version: 3,
            controller_epoch: 2,
            is_simulated: true,
            session_counts: { active: 3 },
            pending_questions: 0,
            pending_approvals: 0,
            recent_actions: [],
          }),
        [`POST ${agentUrl}/pause`]: () =>
          json({ state: "paused", controller_mode: "autonomous", config_version: 4, controller_epoch: 2 }),
      }),
    );

    renderApp(`/w/${WS_GOLKENT}`);
    const rows = await screen.findAllByTestId(`agent-row-${account.id}`);
    expect(rows[0]).toHaveTextContent("@studio_ist");
    expect(rows[0]).toHaveTextContent("Aktif");

    // Click pause button (shows confirmation then executes)
    const pauseBtn = within(rows[0]!).getByRole("button", { name: "Asistanı duraklat" });
    await userEvent.setup().click(pauseBtn);

    // Confirm pause
    const confirmBtn = within(rows[0]!).getAllByRole("button", { name: "Asistanı duraklat" }).pop()!;
    await userEvent.setup().click(confirmBtn);

    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith("/pause"))).toBe(true),
    );
  });

  it("does not offer pause controls to staff", async () => {
    mockApi(
      routes(
        {
          ...reportWith([]),
          [`GET ${BASE}/social-accounts`]: () => json({ items: [account], next_cursor: null }),
          [`GET ${agentUrl}`]: () =>
            json({
              state: "active",
              controller_mode: "autonomous",
              config_version: 3,
              controller_epoch: 2,
              is_simulated: true,
              session_counts: {},
              pending_questions: 0,
              pending_approvals: 0,
              recent_actions: [],
            }),
        },
        STAFF_ME,
      ),
    );

    renderApp(`/w/${WS_GOLKENT}`);
    const rows = await screen.findAllByTestId(`agent-row-${account.id}`);
    expect(within(rows[0]!).queryByRole("button", { name: "Asistanı duraklat" })).toBeNull();
  });
});

describe("Home: week calendar", () => {
  it("counts the week's posts and stories and offers a story on days without one", async () => {
    const soon = new Date(Date.now() + 60_000).toISOString();
    const story = contentItem({
      id: "c5000000-0000-4000-8000-000000000501",
      content_type: "story_image",
      status: "scheduled",
      title: "Sabah Hikayesi",
      scheduled_at: soon,
    });
    const post = contentItem({ id: "c5000000-0000-4000-8000-000000000502", status: "scheduled", title: "Kampanya", scheduled_at: soon });

    mockApi(routes({ ...reportWith([]), [`GET ${BASE}/content-items`]: () => json({ items: [story, post], next_cursor: null }) }));
    renderApp(`/w/${WS_GOLKENT}`);

    const week = await screen.findByTestId("week-strip");
    expect(within(week).getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByTestId("week-summary")).toHaveTextContent("Gelecek 7 gün: 1 gönderi · 1 hikaye");
    // Six days have no story; the day with one does not offer another.
    const gaps = within(week).getAllByRole("button", { name: /Hikaye yok: hikaye hazırla/ });
    expect(gaps).toHaveLength(6);
    expect(within(week).getByText(/1 gönderi, 1 hikaye/)).toBeInTheDocument();
    const list = screen.getByTestId("upcoming-list");
    expect(within(list).getByText("Sabah Hikayesi")).toBeInTheDocument();
    expect(within(list).getAllByText("Hikaye").length).toBeGreaterThan(0);

    await userEvent.setup().click(gaps[0]!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});

describe("Home: appointments card", () => {
  it("renders upcoming appointments without exposing customer contact", async () => {
    const appt = {
      id: "c6000000-0000-4000-8000-000000000001",
      calendar_connection_id: "c7000000-0000-4000-8000-000000000001",
      conversation_id: "c8000000-0000-4000-8000-000000000001",
      customer_identity_id: null,
      external_event_id: null,
      title: "Pilates Dersi",
      description: null,
      customer_name: "Ayşe Kaya",
      customer_contact: "+905551234567", // MUST NOT appear on Today card
      start_at: new Date().toISOString(),
      end_at: new Date(Date.now() + 3600_000).toISOString(),
      timezone: "Europe/Istanbul",
      status: "confirmed",
      created_by_source: "agent",
    };

    mockApi(
      routes({
        ...reportWith([]),
        [`GET ${BASE}/calendar`]: () =>
          json({
            items: [
              {
                id: "c7000000-0000-4000-8000-000000000001",
                provider_kind: "google",
                external_account_id: "ext",
                account_email: "test@example.com",
                calendar_id: "primary",
                calendar_summary: "Main",
                calendar_timezone: "Europe/Istanbul",
                connected_at: "2026-10-01T00:00:00Z",
                disconnected_at: null,
                created_at: "2026-10-01T00:00:00Z",
              },
            ],
          }),
        [`GET ${BASE}/calendar/appointments`]: () => json({ items: [appt] }),
      }),
    );

    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("appointments-card");
    expect(await within(card).findByText("Ayşe Kaya")).toBeInTheDocument();
    expect(within(card).getByText("Pilates Dersi")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Konuşmayı aç/i })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/inbox/${appt.conversation_id}`,
    );
    // Never expose customer phone or contact on Today
    expect(within(card).queryByText("+905551234567")).toBeNull();
  });

  it("shows the first three and says how many more there are, keeping the total in the header", async () => {
    const connection = {
      id: "c7000000-0000-4000-8000-000000000001", provider_kind: "google", external_account_id: "ext",
      account_email: "test@example.com", calendar_id: "primary", calendar_summary: "Main",
      calendar_timezone: "Europe/Istanbul", connected_at: "2026-10-01T00:00:00Z", disconnected_at: null,
      created_at: "2026-10-01T00:00:00Z",
    };
    const appointments = [1, 2, 3, 4, 5].map((n) => ({
      id: `c6000000-0000-4000-8000-00000000000${n}`, calendar_connection_id: connection.id, conversation_id: null,
      customer_identity_id: null, external_event_id: null, title: "Grup dersi", description: null,
      customer_name: `Müşteri ${n}`, customer_contact: null,
      start_at: new Date(Date.now() + n * 60_000).toISOString(), end_at: new Date(Date.now() + n * 60_000 + 3600_000).toISOString(),
      timezone: "Europe/Istanbul", status: "confirmed", created_by_source: "agent",
    }));
    mockApi(routes({
      ...reportWith([]),
      [`GET ${BASE}/calendar`]: () => json({ items: [connection] }),
      [`GET ${BASE}/calendar/appointments`]: () => json({ items: appointments }),
    }));
    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("appointments-card");
    expect(await within(card).findByText("Müşteri 1")).toBeInTheDocument();
    expect(within(card).getAllByRole("listitem")).toHaveLength(3);
    expect(within(card).queryByText("Müşteri 4")).toBeNull();
    expect(within(card).getByTestId("appointments-more")).toHaveTextContent("+2 randevu daha");
    expect(within(card).getByText("5")).toBeInTheDocument();
  });
});

describe("Home: instagram insights card", () => {
  it("renders reach, views, and interactions with sparkline when status is ok", async () => {
    const acc = socialAccount({
      id: "a1000000-0000-4000-8000-000000000001",
      username: "kadikoy_yoga",
      status: "connected",
      is_simulated: true,
    });

    mockApi(
      routes({
        ...reportWith([]),
        ...accounts(acc),
        [`GET ${BASE}/accounts/${acc.id}/insights/summary`]: (req) => {
          const range = req.search.includes("range=28d") ? "28d" : "7d";
          return json({
            account_id: acc.id,
            range,
            status: "ok",
            updated_at: "2026-11-10T12:00:00Z",
            reach: range === "28d" ? 4800 : 1200,
            reach_delta_pct: 15,
            views: range === "28d" ? 9600 : 2400,
            views_delta_pct: 22,
            interactions: range === "28d" ? 720 : 180,
            interactions_delta_pct: 8,
            follower_count: 1420,
            follower_delta: 14,
            sparkline: [
              { date: "2026-11-04", reach: 140, views: 280 },
              { date: "2026-11-05", reach: 180, views: 320 },
            ],
            is_simulated: true,
          });
        },
      }),
    );

    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("insights-performance-card");
    expect(within(card).getByText("Instagram Performansı")).toBeInTheDocument();
    const kpis = within(card).getByTestId("insights-kpis");
    expect(within(kpis).getByText("1.200")).toBeInTheDocument();
    expect(within(kpis).getByText("2.400")).toBeInTheDocument();
    expect(within(kpis).getByText("180")).toBeInTheDocument();
    expect(within(kpis).getByText("+15%")).toBeInTheDocument();
    // The trend has a table equivalent for assistive technology.
    expect(within(card).getByRole("table", { name: "Günlük Eğilim" })).toBeInTheDocument();

    // Toggle to 28d
    await userEvent.setup().click(within(card).getByRole("button", { name: "28 Gün" }));
    expect(await within(within(card).getByTestId("insights-kpis")).findByText("4.800")).toBeInTheDocument();
  });

  it("shows permission reconnect warning when status is not_granted", async () => {
    const acc = socialAccount({
      id: "a1000000-0000-4000-8000-000000000001",
      username: "kadikoy_yoga",
      status: "connected",
      is_simulated: false,
    });

    mockApi(
      routes({
        ...reportWith([]),
        ...accounts(acc),
        [`GET ${BASE}/accounts/${acc.id}/insights/summary`]: () =>
          json({
            account_id: acc.id,
            range: "7d",
            status: "not_granted",
            updated_at: null,
            reach: 0,
            reach_delta_pct: null,
            views: 0,
            views_delta_pct: null,
            interactions: 0,
            interactions_delta_pct: null,
            follower_count: null,
            follower_delta: null,
            sparkline: [],
            is_simulated: false,
          }),
      }),
    );

    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("insights-performance-card");
    expect(within(card).getByText("Instagram Insights İzni Eksik")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Hesabı Yeniden Bağla/i })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
  });
});

describe("Home: production failure regressions", () => {
  const account = socialAccount({ id: "a1000000-0000-4000-8000-000000000001" });
  const agentUrl = `${BASE}/accounts/${account.id}/agent`;
  const zeroReport = () => reportWith(FULL_METRICS.map((m) => ({ ...m, value: 0 })));

  it("uses exact attention totals without fetching capped comment previews", async () => {
    const requests = mockApi(routes({
      ...zeroReport(), ...accounts(account),
      [`GET ${agentUrl}`]: () => json(HEALTHY_AGENT),
      [`GET ${BASE}/home/attention`]: () => json({ drafts: 61, unanswered_comments: 32 }),
    }));
    renderApp(`/w/${WS_GOLKENT}`);
    await waitFor(() => expect(screen.getByTestId("attention-drafts")).toHaveTextContent("61"));
    expect(screen.getByTestId("attention-comments")).toHaveTextContent("32");
    expect(requests.some((r) => r.path.endsWith("/comments"))).toBe(false);
    expect(screen.queryByTestId("attention-none")).toBeNull();
  });

  it("never shows all-clear when attention counts fail", async () => {
    mockApi(routes({ ...zeroReport(), [`GET ${BASE}/home/attention`]: () => problem(503, "INTERNAL_ERROR") }));
    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("home-attention");
    expect(await within(card).findByRole("alert")).toBeInTheDocument();
    expect(within(card).getByTestId("attention-comments")).toHaveTextContent(tr.core.unavailable);
    expect(screen.queryByTestId("attention-none")).toBeNull();
  });

  it("keeps pending counts unknown", async () => {
    mockApi(routes({ ...zeroReport(), [`GET ${BASE}/home/attention`]: () => new Promise<Response>(() => {}) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const row = await screen.findByTestId("attention-comments");
    expect(row).toHaveTextContent(tr.core.unavailable);
    expect(screen.queryByTestId("attention-none")).toBeNull();
  });

  it.each(["inactive", "paused"])("shows the actual %s assistant state", async (state) => {
    mockApi(routes({ ...zeroReport(), ...accounts(account), [`GET ${agentUrl}`]: () => json({ ...HEALTHY_AGENT, state }) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const rows = await screen.findAllByTestId(`agent-row-${account.id}`);
    const row = rows[0]!;
    await waitFor(() => expect(row).toHaveTextContent(state === "inactive" ? tr.home.agentStatus.inactive : tr.home.agentStatus.paused));
    expect(within(row).queryByText(tr.home.agentStatus.active)).toBeNull();
    if (state === "inactive") expect(within(row).queryByRole("button")).toBeNull();
  });

  it("does not mark an assistant active after its overview fails", async () => {
    mockApi(routes({ ...zeroReport(), ...accounts(account), [`GET ${agentUrl}`]: () => problem(503, "INTERNAL_ERROR") }));
    renderApp(`/w/${WS_GOLKENT}`);
    const row = (await screen.findAllByTestId(`agent-row-${account.id}`))[0]!;
    await waitFor(() => expect(row).toHaveTextContent(tr.core.unavailable));
    expect(within(row).queryByText(tr.home.agentStatus.active)).toBeNull();
    expect(within(row).queryByRole("button")).toBeNull();
  });

  it("shows loading rather than active before the overview arrives", async () => {
    mockApi(routes({ ...zeroReport(), ...accounts(account), [`GET ${agentUrl}`]: () => new Promise<Response>(() => {}) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const row = (await screen.findAllByTestId(`agent-row-${account.id}`))[0]!;
    expect(row).toHaveTextContent(tr.common.loading);
    expect(within(row).queryByText(tr.home.agentStatus.active)).toBeNull();
  });

  it.each(["pause", "resume"] as const)("keeps failed %s visible and retryable", async (command) => {
    mockApi(routes({ ...zeroReport(), ...accounts(account),
      [`GET ${agentUrl}`]: () => json({ ...HEALTHY_AGENT, state: command === "pause" ? "active" : "paused" }),
      [`POST ${agentUrl}/${command}`]: () => problem(409, "VERSION_CONFLICT"),
    }));
    renderApp(`/w/${WS_GOLKENT}`);
    const row = (await screen.findAllByTestId(`agent-row-${account.id}`))[0]!;
    const user = userEvent.setup();
    await user.click(await within(row).findByRole("button", { name: tr.home.agentStatus[command] }));
    await user.click(within(row).getByRole("button", { name: tr.home.agentStatus[command] }));
    expect(await within(row).findByRole("alert")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: tr.home.agentStatus[command] })).toBeEnabled();
  });

  it.each(["calendar", "calendar/appointments", "activity"])("displays %s failures without an empty-state claim", async (endpoint) => {
    mockApi(routes({ ...zeroReport(), [`GET ${BASE}/${endpoint}`]: () => problem(403, "FORBIDDEN") }));
    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId(endpoint === "activity" ? "activity-feed-card" : "appointments-card");
    expect(await within(card).findByRole("alert")).toBeInTheDocument();
    expect(within(card).queryByTestId("activity-empty")).toBeNull();
    expect(within(card).queryByTestId("appointments-empty")).toBeNull();
    if (endpoint !== "activity") expect(screen.queryByTestId("appointments-card-unconnected")).toBeNull();
  });

  it("does not fabricate scheduling gaps after content fails", async () => {
    mockApi(routes({ ...zeroReport(), [`GET ${BASE}/content-items`]: () => problem(403, "FORBIDDEN") }));
    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("home-upcoming");
    expect((await within(card).findAllByRole("alert")).length).toBeGreaterThan(0);
    expect(within(card).queryByTestId("week-strip")).toBeNull();
    expect(within(card).queryByTestId("week-summary")).toBeNull();
    expect(within(card).queryByTestId("upcoming-empty")).toBeNull();
  });

  it("labels partial insights and leaves missing totals unavailable", async () => {
    mockApi(routes({ ...zeroReport(), ...accounts(account), [`GET ${agentUrl}`]: () => json(HEALTHY_AGENT),
      [`GET ${BASE}/accounts/${account.id}/insights/summary`]: () => json({ account_id: account.id,
        range: "7d", status: "partial", current_days_covered: 2, previous_days_covered: 0,
        updated_at: null, reach: null, views: null, interactions: null, reach_delta_pct: null,
        views_delta_pct: null, interactions_delta_pct: null, follower_count: null,
        follower_delta: null, sparkline: [{date:"2026-11-08",reach:null,views:null},{date:"2026-11-09",reach:10,views:20}], is_simulated: false }),
    }));
    renderApp(`/w/${WS_GOLKENT}`);
    const card = await screen.findByTestId("insights-performance-card");
    expect(await within(card).findByTestId("insights-partial")).toBeInTheDocument();
    expect(within(within(card).getByTestId("insights-kpis")).getAllByText(tr.core.unavailable)).toHaveLength(3);
    expect(within(card).queryByText("+100%")).toBeNull();
    expect(within(within(card).getByTestId("insights-kpis")).queryByText("0")).toBeNull();
  });
});
