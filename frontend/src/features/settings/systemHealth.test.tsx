import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SystemHealth } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const HEALTH = `GET ${BASE}/system-health`;
const PAGE = `/w/${WS_GOLKENT}/more/settings/system-health`;

function health(overrides: Partial<SystemHealth> = {}): SystemHealth {
  return {
    generated_at: "2026-10-21T10:00:00Z",
    window_hours: 24,
    accounts: [
      {
        id: "a1000000-0000-4000-8000-000000000001",
        username: "golkent.demo",
        status: "degraded",
        last_error_code: "PROVIDER_UNAVAILABLE",
        connection_expires_at: null,
        degraded_until: "2026-10-21T10:30:00Z",
        is_simulated: true,
      },
    ],
    operations: {
      counts: [
        { type: "send_reply", status: "succeeded", count: 12 },
        { type: "send_reply", status: "failed", count: 2 },
        { type: "publish_content", status: "outcome_unknown", count: 1 },
      ],
      latest_failures: [
        {
          id: "b1000000-0000-4000-8000-000000000001",
          type: "send_reply",
          status: "failed",
          last_error_code: "PROVIDER_RATE_LIMITED",
          occurred_at: "2026-10-21T09:00:00Z",
          is_simulated: true,
        },
      ],
    },
    jobs: { queued: 3, oldest_queued_age_seconds: 300, dead_24h: 1 },
    webhooks: { received_24h: 40, ignored_24h: 2, failed_24h: 1, signature_failures_24h_system_wide: 7 },
    ai: {
      runs: [
        { task: "draft_reply", status: "succeeded", count: 8 },
        { task: "draft_reply", status: "failed", count: 2 },
      ],
      total: 10,
      failed: 2,
      failure_rate: 0.2,
      input_units: 12000,
      output_units: 3400,
      estimated_cost_usd: 0.0123,
      budget_used: 10,
      budget_limit: 500,
    },
    ...overrides,
  };
}

function routes(current: () => Response, extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/social-accounts`]: () => json({ items: [], next_cursor: null }),
    [HEALTH]: current,
    ...extra,
  };
}

describe("the system health screen", () => {
  it("shows every section with the numbers of the response", async () => {
    mockApi(routes(() => json(health())));
    renderApp(PAGE);

    const accounts = await screen.findByTestId("health-accounts");
    expect(within(accounts).getByText("@golkent.demo")).toBeInTheDocument();
    expect(within(accounts).getByTestId("account-status-badge")).toHaveTextContent("kararsız");
    expect(within(accounts).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(accounts).getByText(/13:30/)).toBeInTheDocument(); // degraded_until, Istanbul time

    const operations = screen.getByTestId("health-operations");
    expect(within(operations).getByTestId("op-count-send_reply-succeeded")).toHaveTextContent("12");
    expect(within(operations).getByTestId("op-count-send_reply-failed")).toHaveTextContent("2");
    expect(within(operations).getByTestId("op-count-publish_content-outcome_unknown")).toHaveTextContent("1");
    expect(within(operations).getByText("Yanıt gönderme · başarılı")).toBeInTheDocument();
    expect(within(operations).getByText("Gönderi yayınlama · kontrol ediliyor")).toBeInTheDocument();

    expect(screen.getByTestId("jobs-queued")).toHaveTextContent("3");
    expect(screen.getByTestId("jobs-oldest")).toHaveTextContent("5 dk");
    expect(screen.getByTestId("jobs-dead")).toHaveTextContent("1");

    expect(screen.getByTestId("webhooks-received")).toHaveTextContent("40");
    expect(screen.getByTestId("webhooks-ignored")).toHaveTextContent("2");
    expect(screen.getByTestId("webhooks-failed")).toHaveTextContent("1");

    expect(screen.getByTestId("ai-total")).toHaveTextContent("10");
    expect(screen.getByTestId("ai-failed")).toHaveTextContent("2");
    expect(screen.getByTestId("ai-failure-rate")).toHaveTextContent("%20");
    expect(screen.getByTestId("ai-cost")).toHaveTextContent("$0,0123");
    expect(screen.getByTestId("ai-budget")).toHaveTextContent("10 / 500");
  });

  it("renders error codes through the catalog and never shows a raw code as the explanation", async () => {
    mockApi(routes(() => json(health())));
    renderApp(PAGE);
    const accounts = await screen.findByTestId("health-accounts");
    expect(within(accounts).getByTestId("health-account-error")).not.toHaveTextContent("PROVIDER_UNAVAILABLE");
    expect(within(accounts).getByTestId("health-account-error").textContent).not.toBe("");

    const failure = within(screen.getByTestId("health-operations")).getByTestId("health-failure");
    expect(failure).toHaveTextContent("Yanıt gönderme · başarısız");
    expect(failure).toHaveTextContent("Instagram yavaşlamamızı istedi.");
    expect(failure).not.toHaveTextContent("PROVIDER_RATE_LIMITED");
  });

  it("labels the signature counter as system-wide and shows it (AC-G4)", async () => {
    mockApi(routes(() => json(health())));
    renderApp(PAGE);
    const webhooks = await screen.findByTestId("health-webhooks");
    expect(within(webhooks).getByTestId("webhooks-signature")).toHaveTextContent("7");
    expect(within(webhooks).getByText("Geçersiz imzalı bildirim (tüm sistem)")).toBeInTheDocument();
    expect(within(webhooks).getByText(/tüm sistemi kapsar/)).toBeInTheDocument();
  });

  it("says so when there is nothing to report", async () => {
    mockApi(
      routes(() =>
        json(
          health({
            accounts: [],
            operations: { counts: [], latest_failures: [] },
            jobs: { queued: 0, oldest_queued_age_seconds: null, dead_24h: 0 },
            webhooks: { received_24h: 0, ignored_24h: 0, failed_24h: 0, signature_failures_24h_system_wide: 0 },
            ai: {
              runs: [],
              total: 0,
              failed: 0,
              failure_rate: 0,
              input_units: 0,
              output_units: 0,
              estimated_cost_usd: null,
              budget_used: 0,
              budget_limit: 500,
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);
    expect(await screen.findByText("Bağlı hesap yok.")).toBeInTheDocument();
    expect(screen.getByText("Son 24 saatte işlem yok.")).toBeInTheDocument();
    expect(screen.getByText("Son 24 saatte sorun yok.")).toBeInTheDocument();
    expect(screen.getByTestId("jobs-oldest")).toHaveTextContent("Bekleyen yok");
    expect(screen.getByText("Son 24 saatte yapay zeka çalışması yok.")).toBeInTheDocument();
    expect(screen.getByTestId("ai-cost")).toHaveTextContent("Fiyat tablosu yok");
  });

  it("refreshes on demand", async () => {
    let queued = 3;
    const requests = mockApi(
      routes(() => json(health({ jobs: { queued, oldest_queued_age_seconds: 60, dead_24h: 0 } }))),
    );
    renderApp(PAGE);
    expect(await screen.findByTestId("jobs-queued")).toHaveTextContent("3");

    queued = 9;
    await userEvent.setup().click(screen.getByRole("button", { name: "Yenile" }));

    await waitFor(() => expect(screen.getByTestId("jobs-queued")).toHaveTextContent("9"));
    expect(requests.filter((r) => r.path.endsWith("/system-health"))).toHaveLength(2);
  });

  it("shows the forbidden answer for a role without access instead of numbers", async () => {
    mockApi(routes(() => problem(403, "FORBIDDEN")));
    renderApp(PAGE);
    expect(await screen.findByText("Rolünüz bu işlem için yetkili değil.")).toBeInTheDocument();
    expect(screen.queryByTestId("health-jobs")).not.toBeInTheDocument();
  });
});

describe("the developer panel health check", () => {
  it("runs the check now and reports what it found", async () => {
    const requests = mockApi({
      ...routes(() => json(health())),
      "GET /api/v1/dev/scripts": () => json([]),
      [`GET /api/v1/dev/workspaces/${WS_GOLKENT}/failure-rules`]: () => json({ items: [], next_cursor: null }),
      "GET /api/v1/dev/jobs": () => json({ items: [], next_cursor: null }),
      [`GET /api/v1/dev/workspaces/${WS_GOLKENT}/simulator/published`]: () => json({ items: [], next_cursor: null }),
      [`POST /api/v1/dev/workspaces/${WS_GOLKENT}/health-check`]: () => json({ checked: 1, recovered: 1 }),
    });
    renderApp(`/w/${WS_GOLKENT}/more/dev`);

    await userEvent.setup().click(await screen.findByRole("button", { name: "Sağlık kontrolünü şimdi çalıştır" }));

    expect(await screen.findByTestId("health-check-result")).toHaveTextContent("Kontrol edilen: 1, düzelen: 1");
    expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/health-check"))).toHaveLength(1);
  });
});
