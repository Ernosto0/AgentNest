import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppNotification, MissedCustomerReport } from "@/api/types";
import i18n from "@/i18n";
import { describeNotification } from "@/features/notifications/describe";
import { notificationTarget } from "@/features/notifications/target";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { item, metricItems } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";
import { shiftDay, todayIn } from "./dates";
import { mondayOf } from "./weeks";

afterEach(() => vi.unstubAllGlobals());

const THIS_WEEK = mondayOf(todayIn("Europe/Istanbul"));
const LAST_WEEK = shiftDay(THIS_WEEK, -7);
const BASE = `/api/v1/workspaces/${WS_GOLKENT}/reports/missed-customers`;
const PAGE = `/w/${WS_GOLKENT}/more/reports/missed-customers`;

function routes(extra: Record<string, (r: never) => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

function link(week: string, key: string) {
  return { api: `${BASE}/${week}/metrics/${key}`, route: `${PAGE}/${week}/${key}` };
}

function missed(week: string, overrides: Partial<MissedCustomerReport> = {}): MissedCustomerReport {
  const m = (key: string, value: number | null, previous: number | null = null) => ({
    key,
    value,
    previous_value: previous,
    link: value === null ? null : link(week, key),
  });
  return {
    week_start: week,
    week_end: shiftDay(week, 6),
    timezone: "Europe/Istanbul",
    period_start: `${week}T00:00:00Z`,
    period_end: `${shiftDay(week, 7)}T00:00:00Z`,
    generated_at: `${shiftDay(week, 7)}T07:00:00Z`,
    is_partial: false,
    hours_available: true,
    has_simulated_data: false,
    metrics: [
      m("after_hours_dms", 4, 1),
      m("first_reply_median_minutes", 31, 12.5),
      m("unanswered_conversations", 2),
      m("answered_questions", 2),
      m("after_hours_price_answers", 1),
    ],
    estimate: {
      status: "ok",
      currency: "TRY",
      amount: "562.50",
      price_questions: 1,
      conversion_rate: "0.05",
      median_price: "11250.00",
      price_count: 2,
      price_inputs: [
        { key: "pricing.membership_monthly", label: "Aylık üyelik", amount: "6000.00", unit: "month" },
        { key: "pricing.membership_3_months", label: "3 aylık üyelik", amount: "16500.00", unit: "package" },
      ],
    },
    ...overrides,
  };
}

describe("weekly missed-customer report", () => {
  it("shows the estimate with its formula and every input, and links each number to its records", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => json(missed(THIS_WEEK)) }));
    renderApp(PAGE);

    const estimate = await screen.findByTestId("missed-estimate");
    expect(estimate).toHaveAttribute("data-status", "ok");
    expect(within(estimate).getByTestId("missed-amount")).toHaveTextContent(/562,50/);
    // The formula names all three factors and the result; nothing is shown without its basis.
    const formula = within(estimate).getByTestId("missed-formula");
    expect(formula).toHaveTextContent("1 fiyat sorusu");
    expect(formula).toHaveTextContent("%5");
    expect(formula).toHaveTextContent(/11\.250,00/);
    expect(formula).toHaveTextContent(/562,50/);
    expect(within(estimate).getByText("Tahmindir, ölçüm değildir")).toBeInTheDocument();
    const inputs = within(within(estimate).getByTestId("missed-price-inputs")).getAllByRole("listitem");
    expect(inputs).toHaveLength(2);
    expect(inputs[0]).toHaveTextContent("Aylık üyelik");
    expect(inputs[0]).toHaveTextContent("ay");

    const dms = screen.getByRole("link", { name: /Mesai saatleri dışında gelen mesaj: 4/ });
    expect(dms).toHaveAttribute("href", `${PAGE}/${THIS_WEEK}/after_hours_dms`);
    expect(screen.getByTestId("missed-after_hours_dms")).toHaveTextContent("Önceki hafta: 1");
    expect(screen.getByRole("link", { name: /İlk yanıta kadar geçen ortanca süre: 31 dk/ })).toBeInTheDocument();
  });

  it("says how many prices the median is over, and that the list is cut when there are more than shown", async () => {
    const base = missed(THIS_WEEK);
    const inputs = Array.from({ length: 20 }, (_, n) => ({ key: `pricing.item_${n}`, label: `Fiyat ${n}`, amount: `${(n + 1) * 100}.00`, unit: null }));
    mockApi(routes({ [`GET ${BASE}`]: () => json({ ...base, estimate: { ...base.estimate, price_inputs: inputs, price_count: 25 } }) }));
    renderApp(PAGE);
    const count = await screen.findByTestId("missed-price-count");
    expect(count).toHaveTextContent("Ortanca, doğrulanmış 25 fiyat üzerinden alındı.");
    expect(count).toHaveTextContent("25 fiyattan 20 tanesi gösteriliyor");
    expect(within(screen.getByTestId("missed-price-inputs")).getAllByRole("listitem")).toHaveLength(20);
  });

  it("does not claim a cut list when every price is shown", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => json(missed(THIS_WEEK)) }));
    renderApp(PAGE);
    const count = await screen.findByTestId("missed-price-count");
    expect(count).toHaveTextContent("doğrulanmış 2 fiyat üzerinden");
    expect(count).not.toHaveTextContent("gösteriliyor");
  });

  it("shows counts only, no lira, when there is no verified price", async () => {
    mockApi(
      routes({
        [`GET ${BASE}`]: () =>
          json(
            missed(THIS_WEEK, {
              estimate: { status: "no_verified_price", currency: "TRY", amount: null, price_questions: 1, conversion_rate: "0.05", median_price: null, price_inputs: [], price_count: 0 },
            }),
          ),
      }),
    );
    renderApp(PAGE);
    const estimate = await screen.findByTestId("missed-estimate");
    expect(estimate).toHaveAttribute("data-status", "no_verified_price");
    expect(within(estimate).getByTestId("missed-counts-only")).toHaveTextContent("lira tutarı gösterilmez");
    expect(screen.queryByTestId("missed-amount")).toBeNull();
    expect(screen.queryByTestId("missed-formula")).toBeNull();
    expect(within(estimate).getByRole("link", { name: "Fiyatlarınızı ekleyin" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/knowledge/pricing`);
    // The counts are still there.
    expect(screen.getByRole("link", { name: /Mesai saatleri dışında gelen mesaj: 4/ })).toBeInTheDocument();
  });

  it("says the after-hours numbers are not known when the opening hours are not verified", async () => {
    mockApi(
      routes({
        [`GET ${BASE}`]: () =>
          json(
            missed(THIS_WEEK, {
              hours_available: false,
              metrics: [
                { key: "after_hours_dms", value: null, previous_value: null, link: null },
                { key: "after_hours_price_answers", value: null, previous_value: null, link: null },
                { key: "unanswered_conversations", value: 2, previous_value: null, link: link(THIS_WEEK, "unanswered_conversations") },
              ],
              estimate: { status: "hours_missing", currency: "TRY", amount: null, price_questions: null, conversion_rate: "0.05", median_price: null, price_inputs: [], price_count: 0 },
            }),
          ),
      }),
    );
    renderApp(PAGE);
    const estimate = await screen.findByTestId("missed-estimate");
    expect(within(estimate).getByTestId("missed-counts-only")).toHaveTextContent("Çalışma saatleriniz henüz doğrulanmadığı için");
    expect(within(estimate).getByRole("link", { name: "Çalışma saatlerinizi ekleyin" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/knowledge/hours`);
    expect(within(screen.getByTestId("missed-after_hours_dms")).getByText("Bilinmiyor")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Yanıtsız kalan konuşma: 2/ })).toBeInTheDocument();
  });

  it("says so when the week has nothing to report", async () => {
    mockApi(
      routes({
        [`GET ${BASE}`]: () =>
          json(
            missed(THIS_WEEK, {
              metrics: ["after_hours_dms", "unanswered_conversations", "answered_questions", "after_hours_price_answers"].map((key) => ({ key, value: 0, previous_value: 0, link: link(THIS_WEEK, key) })),
            }),
          ),
      }),
    );
    renderApp(PAGE);
    expect(await screen.findByText("Bu hafta raporlanacak müşteri mesajı yok")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mesai saatleri dışında gelen mesaj/ })).toBeNull();
  });

  it("marks the week in progress and never offers a week after this one", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => json(missed(THIS_WEEK, { is_partial: true, period_end: `${THIS_WEEK}T11:35:00Z` })) }));
    renderApp(PAGE);
    expect(await screen.findByTestId("missed-as-of")).toHaveTextContent("Hafta devam ediyor");
    expect(screen.getByRole("button", { name: "Sonraki hafta" })).toBeDisabled();
  });

  it("steps back a week and returns to this week", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}`]: () => json(missed(requests.at(-1)!.search.includes(LAST_WEEK) ? LAST_WEEK : THIS_WEEK)),
      }),
    );
    renderApp(PAGE);
    await screen.findByTestId("missed-estimate");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Önceki hafta" }));
    await waitFor(() => expect(requests.some((r) => r.path === BASE && r.search === `?week_start=${LAST_WEEK}`)).toBe(true));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Mesai saatleri dışında gelen mesaj: 4/ })).toHaveAttribute("href", `${PAGE}/${LAST_WEEK}/after_hours_dms`),
    );
    await user.click(screen.getByRole("button", { name: "Bu haftaya dön" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sonraki hafta" })).toBeDisabled());
  });

  it("opens the week a notification points to, and not a week after this one", async () => {
    const requests = mockApi(routes({ [`GET ${BASE}`]: () => json(missed(LAST_WEEK)) }));
    renderApp(`${PAGE}?week=${LAST_WEEK}`);
    await screen.findByTestId("missed-estimate");
    expect(requests.some((r) => r.path === BASE && r.search === `?week_start=${LAST_WEEK}`)).toBe(true);
    vi.unstubAllGlobals();

    const later = mockApi(routes({ [`GET ${BASE}`]: () => json(missed(THIS_WEEK)) }));
    renderApp(`${PAGE}?week=${shiftDay(THIS_WEEK, 14)}`);
    await waitFor(() => expect(later.some((r) => r.path === BASE)).toBe(true));
    expect(later.find((r) => r.path === BASE)!.search).toBe("");
  });

  it("explains a refused request instead of showing numbers", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => problem(403, "FORBIDDEN") }));
    renderApp(PAGE);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("missed-estimate")).toBeNull();
  });
});

describe("the records behind a weekly number", () => {
  const DRILL = `${BASE}/${LAST_WEEK}/metrics/unanswered_conversations`;

  it("lists as many records as the number says and links back to the week", async () => {
    mockApi(
      routes({
        [`GET ${DRILL}`]: () => json(metricItems("unanswered_conversations", 2, [item(1), item(2)])),
      }),
    );
    renderApp(`${PAGE}/${LAST_WEEK}/unanswered_conversations`);
    expect(await screen.findByTestId("metric-count")).toHaveTextContent("Toplam: 2");
    expect(screen.getAllByTestId("metric-item")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "musteri_1" })).toHaveAttribute("href", expect.stringContaining("/inbox/"));
    expect(screen.getByRole("link", { name: "Haftalık rapora dön" })).toHaveAttribute("href", `${PAGE}?week=${LAST_WEEK}`);
  });

  it("is not found for a metric the weekly report does not have", async () => {
    mockApi(routes());
    renderApp(`${PAGE}/${LAST_WEEK}/inbound_messages`);
    await waitFor(() => expect(screen.queryByTestId("metric-count")).toBeNull());
    expect(screen.queryByTestId("metric-item")).toBeNull();
  });
});

describe("the weekly report notification", () => {
  const notice = {
    id: "n1",
    type: "report.missed_customers_ready",
    severity: "info",
    params: { week_start: "2026-03-09", after_hours_dms: 4, unanswered_conversations: 2 },
    is_simulated: false,
    read_at: null,
    created_at: "2026-03-16T07:00:00Z",
    subject_type: null,
    subject_id: null,
  } as unknown as AppNotification;

  it("reads in both languages, with counts only, and opens that week", () => {
    expect(describeNotification(i18n.getFixedT("tr"), notice, "tr")).toBe(
      "Haftalık kaçan müşteri raporu: 4 mesaj mesai dışında geldi, 2 konuşma yanıtsız kaldı",
    );
    expect(describeNotification(i18n.getFixedT("en"), notice, "en")).toBe(
      "Weekly missed-customer report: 4 messages came after hours, 2 conversations got no reply",
    );
    expect(notificationTarget("w1", notice)).toBe("/w/w1/more/reports/missed-customers?week=2026-03-09");
  });
});
