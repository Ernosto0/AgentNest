import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReplyUsage } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const SETTINGS = `/w/${WS_GOLKENT}/more/settings`;
const TODAY = `/w/${WS_GOLKENT}`;

const asRole = (role: "owner" | "manager" | "staff") => ({
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
});

function usage(overrides: Partial<ReplyUsage> = {}): ReplyUsage {
  return {
    plan: "growth",
    status: "trial",
    monthly_quota: 2500,
    quota_override: null,
    quota: 2500,
    used: 1200,
    grace_limit: 2750,
    period_start: "2026-10-15T09:00:00Z",
    period_end: "2026-11-15T09:00:00Z",
    state: "normal",
    ...overrides,
  };
}

function routes(me: typeof ME, current: ReplyUsage, seen: RecordedRequest[] = []) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/usage`]: (request: RecordedRequest) => {
      seen.push(request);
      return json(current);
    },
  };
}

describe("Settings: plan and AI replies", () => {
  it("shows the plan, the used and allowed replies, the state and the period end", async () => {
    mockApi(routes(ME, usage()));
    renderApp(SETTINGS);

    const meter = await screen.findByTestId("usage-meter");
    expect(within(meter).getByText("İşletme")).toBeInTheDocument();
    expect(within(meter).getByText("Deneme")).toBeInTheDocument();
    expect(within(meter).getByText("1.200 / 2.500 yanıt")).toBeInTheDocument();
    const bar = within(meter).getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "1200");
    expect(bar).toHaveAttribute("aria-valuemax", "2500");
    expect(within(meter).getByTestId("usage-state")).toHaveTextContent("Yapay zeka taslakları kullanılabilir.");
    expect(within(meter).getByText(/15 Kas 2026/)).toBeInTheDocument();
    // the section is in the page navigation
    expect(screen.getAllByRole("link", { name: "Plan ve yapay zeka yanıtları" }).length).toBeGreaterThan(0);
  });

  it("says when the quota is a custom one", async () => {
    mockApi(routes(ME, usage({ plan: "starter", quota_override: 800, quota: 800, grace_limit: 880 })));
    renderApp(SETTINGS);
    const meter = await screen.findByTestId("usage-meter");
    expect(within(meter).getByText("Başlangıç")).toBeInTheDocument();
    expect(within(meter).getByText("Çalışma alanınız için özel yanıt hakkı tanımlı")).toBeInTheDocument();
    expect(within(meter).getByText("1.200 / 800 yanıt")).toBeInTheDocument();
    expect(within(meter).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "800"); // never past full
  });

  it.each([
    ["warning", "Bu ayki yapay zeka yanıt hakkınızın %80'i kullanıldı."],
    ["grace", "Aylık yanıt hakkı doldu. Taslaklar %10 ek hakla devam eder, ardından duraklar."],
  ] as const)("explains the %s state", async (state, text) => {
    mockApi(routes(ME, usage({ state, used: state === "warning" ? 2000 : 2600 })));
    renderApp(SETTINGS);
    const message = await screen.findByTestId("usage-state");
    expect(message).toHaveTextContent(text);
    expect(message).toHaveAttribute("role", "status");
  });

  it("announces the paused state and says what the owner can do", async () => {
    mockApi(routes(ME, usage({ state: "paused", used: 2750 })));
    renderApp(SETTINGS);
    const message = within(await screen.findByTestId("usage-meter")).getByRole("alert");
    expect(message).toHaveTextContent("Yapay zeka yanıtları duraklatıldı");
    expect(message).toHaveTextContent("kendiniz yanıtlayabilirsiniz");
    expect(message).toHaveTextContent("Taslaklar yeni dönemde veya plan değişince devam eder");
  });

  it("is shown to a manager", async () => {
    mockApi(routes(asRole("manager"), usage()));
    renderApp(SETTINGS);
    expect(await screen.findByTestId("usage-meter")).toBeInTheDocument();
  });

  it("is not shown to staff, and nothing is fetched for them", async () => {
    const seen: RecordedRequest[] = [];
    mockApi(routes(asRole("staff"), usage(), seen));
    renderApp(SETTINGS);
    await screen.findByRole("heading", { name: "Ayarlar" });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Hesap" })).toBeInTheDocument());
    expect(screen.queryByTestId("usage-meter")).toBeNull();
    expect(screen.queryByRole("link", { name: "Plan ve yapay zeka yanıtları" })).toBeNull();
    expect(seen).toHaveLength(0);
  });
});

describe("Today: the allowance notice", () => {
  it("is silent while usage is normal", async () => {
    mockApi(routes(ME, usage({ used: 100 })));
    renderApp(TODAY);
    await screen.findByTestId("home-numbers");
    expect(screen.queryByTestId("usage-notice")).toBeNull();
  });

  it("shows up from 80% with the numbers and a link to the details", async () => {
    mockApi(routes(ME, usage({ state: "warning", used: 2000 })));
    renderApp(TODAY);
    const notice = await screen.findByTestId("usage-notice");
    expect(notice).toHaveAttribute("data-state", "warning");
    expect(notice).toHaveTextContent("Bu ayki yapay zeka yanıt hakkınızın %80'i kullanıldı.");
    expect(notice).toHaveTextContent("2.000 / 2.500 yanıt");
    expect(within(notice).getByRole("link", { name: "Plan ve kullanımı gör" })).toHaveAttribute(
      "href",
      `${SETTINGS}#usage`,
    );
    expect(notice).toHaveAttribute("role", "status");
  });

  it("is an alert when drafting is paused", async () => {
    mockApi(routes(ME, usage({ state: "paused", used: 2750 })));
    renderApp(TODAY);
    const notice = await screen.findByTestId("usage-notice");
    expect(notice).toHaveAttribute("role", "alert");
    expect(notice).toHaveTextContent("Yapay zeka yanıtları duraklatıldı");
  });

  it("is not shown to staff", async () => {
    const seen: RecordedRequest[] = [];
    mockApi(routes(asRole("staff"), usage({ state: "paused", used: 2750 }), seen));
    renderApp(TODAY);
    await screen.findByTestId("home-numbers");
    expect(screen.queryByTestId("usage-notice")).toBeNull();
    expect(seen).toHaveLength(0);
  });
});
