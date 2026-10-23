import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DailyReport as Report } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { REPORT_BASE, item, metric, metricItems, report } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";
import { shiftDay, todayIn } from "./dates";

afterEach(() => vi.unstubAllGlobals());

/** The nth element, failing loudly when the list is shorter than the test expects. */
function nth<T>(list: T[], index: number): T {
  const found = list[index];
  if (found === undefined) throw new Error(`expected at least ${index + 1} elements`);
  return found;
}

const TODAY = todayIn("Europe/Istanbul");
const YESTERDAY = shiftDay(TODAY, -1);
const REPORT_URL = `/w/${WS_GOLKENT}/more/reports`;

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m)),
};

function routes(extra: Record<string, (r: never) => Response> = {}, me = ME) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

describe("daily report", () => {
  it("keeps the saved numbers and explains missing legacy evidence", async () => {
    mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY, { evidence_complete: false })) }));
    renderApp(`${REPORT_URL}?date=${YESTERDAY}`);
    expect(await screen.findByText(/Bu eski raporun ayrıntı kayıtları saklanmamış/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gelen mesaj: 15" })).toBeInTheDocument();
  });

  it("preserves a saved report and explains why retention prevents regeneration", async () => {
    mockApi(routes({
      [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      [`POST ${REPORT_BASE}/generate`]: () => problem(409, "REPORT_SOURCES_RETAINED_OUT"),
    }));
    renderApp(`${REPORT_URL}?date=${YESTERDAY}`);
    await screen.findByRole("link", { name: "Gelen mesaj: 15" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Yeniden oluştur" }));
    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("bu rapor eksiksiz yeniden oluşturulamıyor");
    expect(error).toHaveTextContent("Daha önce kaydedilmiş raporu kullanın veya başka bir gün seçin.");
    expect(screen.getByRole("link", { name: "Gelen mesaj: 15" })).toBeInTheDocument();
  });

  it("renders every number as a link to its drill-down and hides what is zero", async () => {
    mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(TODAY)) }));
    renderApp(REPORT_URL);

    await screen.findByRole("heading", { name: "Mesajlar" });

    const links: [string, string, string][] = [
      ["Gelen mesaj: 15", "15", "inbound_messages"],
      ["Ortanca ilk yanıt süresi: 6,5 dk", "6,5 dk", "median_first_response_minutes"],
      ["Onay bekleyen (şu an): 4", "4", "pending_approvals_now"],
      ["Bağlantı hatası: 2", "2", "integration_errors"],
    ];
    for (const [name, text, key] of links) {
      const link = screen.getByRole("link", { name });
      expect(link).toHaveTextContent(text);
      expect(link).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/reports/${TODAY}/${key}`);
    }
    // The approvals row also has the shortcut to the screen that lists them.
    expect(screen.getByRole("link", { name: "Ekranda aç" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/approvals`);

    // Zero metrics and all-zero sections are not shown.
    expect(screen.queryByText("Gönderilen yanıt")).toBeNull();
    expect(screen.queryByText("Yayımlanan gönderi")).toBeNull();
    expect(screen.queryByRole("heading", { name: "İçerik" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Bilgi değişiklikleri" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Sorunlar" })).toBeInTheDocument();
  });

  it("says when the day is not over and shows the badge only for simulated data (AC-E5)", async () => {
    mockApi(
      routes({
        [`GET ${REPORT_BASE}`]: () =>
          json(
            report(TODAY, {
              is_partial: true,
              period_end: `${TODAY}T11:35:00Z`, // 14:35 in Istanbul
              has_simulated_data: true,
            }),
          ),
      }),
    );
    renderApp(REPORT_URL);
    expect(await screen.findByTestId("report-as-of")).toHaveTextContent("14:35 itibarıyla");
    expect(screen.getByTestId("simulated-badge")).toHaveTextContent("SİMÜLASYON");
  });

  it("shows no badge and no partial label for a finished real day", async () => {
    mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(TODAY)) }));
    renderApp(REPORT_URL);
    await screen.findByRole("heading", { name: "Mesajlar" });
    expect(screen.queryByTestId("simulated-badge")).toBeNull();
    expect(screen.queryByTestId("report-as-of")).toBeNull();
  });

  it("says so when nothing was recorded", async () => {
    mockApi(
      routes({
        [`GET ${REPORT_BASE}`]: () =>
          json(
            report(TODAY, {
              metrics: [metric("inbound_messages", 0, "messages", TODAY)],
              summary: { empty: true, text: "Bu gün için kayıt yok.", sections: [] },
            }),
          ),
      }),
    );
    renderApp(REPORT_URL);
    expect(await screen.findByText("Bu gün için kayıt yok.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Gelen mesaj/ })).toBeNull();
  });

  it("steps back a day, never past today, and can return to today", async () => {
    const requests = mockApi(
      routes({
        [`GET ${REPORT_BASE}`]: () => {
          const last = requests.at(-1)!;
          return json(report(last.search.includes(YESTERDAY) ? YESTERDAY : TODAY));
        },
      }),
    );
    renderApp(REPORT_URL);
    await screen.findByRole("heading", { name: "Mesajlar" });
    expect(screen.getByRole("button", { name: "Sonraki gün" })).toBeDisabled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Önceki gün" }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Gelen mesaj: 15" })).toHaveAttribute(
        "href",
        `/w/${WS_GOLKENT}/more/reports/${YESTERDAY}/inbound_messages`,
      ),
    );
    expect(requests.some((r) => r.path === REPORT_BASE && r.search === `?date=${YESTERDAY}`)).toBe(true);
    expect(screen.getByRole("button", { name: "Sonraki gün" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Bugüne dön" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sonraki gün" })).toBeDisabled());
  });

  it("opens the day a command result points to, and not a day after today", async () => {
    const requests = mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)) }));
    renderApp(`${REPORT_URL}?date=${YESTERDAY}`);
    await screen.findByRole("heading", { name: "Mesajlar" });
    expect(requests.some((r) => r.path === REPORT_BASE && r.search === `?date=${YESTERDAY}`)).toBe(true);
    vi.unstubAllGlobals();

    const later = mockApi(routes({ [`GET ${REPORT_BASE}`]: () => json(report(TODAY)) }));
    renderApp(`${REPORT_URL}?date=${shiftDay(TODAY, 3)}`);
    await waitFor(() => expect(later.some((r) => r.path === REPORT_BASE)).toBe(true));
    expect(later.find((r) => r.path === REPORT_BASE)!.search).toBe("");
  });

  it("lets the owner generate the report again and shows the new numbers", async () => {
    let generated: Report | null = null;
    const requests = mockApi(
      routes({
        [`GET ${REPORT_BASE}`]: () => json(generated ?? report(TODAY)),
        [`POST ${REPORT_BASE}/generate`]: () => {
          generated = report(TODAY, {
            metrics: [metric("inbound_messages", 21, "messages", TODAY)],
            summary: { empty: false, text: "", sections: [{ section: "messages", title: "Mesajlar", lines: [] }] },
          });
          return json(generated);
        },
      }),
    );
    renderApp(REPORT_URL);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Yeniden oluştur" }));
    expect(await screen.findByRole("link", { name: "Gelen mesaj: 21" })).toBeInTheDocument();
    const post = requests.find((r) => r.method === "POST")!;
    expect(post.body).toEqual({ date: TODAY });
    expect(post.headers.get("X-CSRF-Token")).toBe("csrf-token-for-tests");
  });

  it("shows staff the inbox sections only, with no regenerate button", async () => {
    mockApi(
      routes(
        {
          [`GET ${REPORT_BASE}`]: () =>
            json(
              report(TODAY, {
                metrics: [metric("inbound_messages", 15, "messages", TODAY)],
                summary: { empty: false, text: "", sections: [{ section: "messages", title: "Mesajlar", lines: [] }] },
              }),
            ),
        },
        STAFF_ME,
      ),
    );
    renderApp(REPORT_URL);
    expect(await screen.findByRole("link", { name: "Gelen mesaj: 15" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Onaylar" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Sorunlar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Yeniden oluştur" })).toBeNull();
    // Every link on the screen leads into the report itself: nothing a staff member may not open.
    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href")!;
      if (href.includes("/more/reports/")) expect(href).toMatch(/\/inbound_messages$/);
    }
  });
});

describe("the records behind a number", () => {
  const DRILL = `${REPORT_BASE}/${YESTERDAY}/metrics/inbound_messages`;
  const ROUTE = `${REPORT_URL}/${YESTERDAY}/inbound_messages`;

  it("pins requests, pagination and return navigation to the linked report generation", async () => {
    const snapshot = "b0000000-0000-4000-8000-000000000001";
    const requests = mockApi(routes({
      [`GET ${DRILL}`]: () => {
        const search = requests.at(-1)!.search;
        return json({
          ...metricItems("inbound_messages", 2, search.includes("cursor=next") ? [item(2)] : [item(1)], search.includes("cursor=next") ? null : "next"),
          snapshot_id: snapshot,
        });
      },
      [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY, { snapshot_id: snapshot })),
    }));
    renderApp(`${ROUTE}?snapshot_id=${snapshot}`);
    await screen.findByTestId("metric-item");
    await userEvent.setup().click(screen.getByRole("button", { name: "Daha fazla göster" }));
    await waitFor(() => expect(screen.getAllByTestId("metric-item")).toHaveLength(2));
    expect(requests.filter((r) => r.path === DRILL).every((r) => r.search.includes(`snapshot_id=${snapshot}`))).toBe(true);
    expect(requests.some((r) => r.path === DRILL && r.search.includes("cursor=next"))).toBe(true);
    const back = screen.getByRole("link", { name: "Rapora dön" });
    expect(back).toHaveAttribute("href", `${REPORT_URL}?date=${YESTERDAY}&snapshot_id=${snapshot}`);
    await userEvent.setup().click(back);
    await screen.findByRole("heading", { name: "Günlük rapor" });
    expect(requests.filter((r) => r.path === REPORT_BASE).every((r) => r.search.includes(`snapshot_id=${snapshot}`))).toBe(true);
  });

  it("explains unavailable legacy detail instead of showing current records", async () => {
    mockApi(routes({
      [`GET ${DRILL}`]: () => problem(409, "REPORT_EVIDENCE_UNAVAILABLE"),
      [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY, { evidence_complete: false })),
    }));
    renderApp(ROUTE);
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu eski raporun ayrıntı kayıtları saklanmamış.");
    expect(screen.queryByTestId("metric-item")).toBeNull();
  });

  it("lists as many records as the number says, each linking to its screen", async () => {
    const rows = [item(1), item(2, { is_simulated: true }), item(3)];
    mockApi(
      routes({
        [`GET ${DRILL}`]: () => json(metricItems("inbound_messages", 3, rows)),
        [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      }),
    );
    renderApp(ROUTE);

    expect(await screen.findByTestId("metric-count")).toHaveTextContent("Toplam: 3");
    const list = screen.getAllByTestId("metric-item");
    expect(list).toHaveLength(3); // the number in the header equals the records shown
    expect(within(nth(list, 0)).getByRole("link", { name: "musteri_1" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/inbox/c0000000-0000-4000-8000-000000000001`,
    );
    expect(within(nth(list, 1)).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(nth(list, 0)).queryByTestId("simulated-badge")).toBeNull();
    expect(screen.getByRole("heading", { name: "Gelen mesaj" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rapora dön" })).toHaveAttribute("href", `${REPORT_URL}?date=${YESTERDAY}`);
  });

  it("pages with the cursor until the count is reached", async () => {
    const requests = mockApi(
      routes({
        [`GET ${DRILL}`]: () => {
          const last = requests.at(-1)!;
          return json(
            last.search.includes("cursor=next")
              ? metricItems("inbound_messages", 3, [item(3)])
              : metricItems("inbound_messages", 3, [item(1), item(2)], "next"),
          );
        },
        [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      }),
    );
    renderApp(ROUTE);
    expect(await screen.findAllByTestId("metric-item")).toHaveLength(2);
    await userEvent.setup().click(screen.getByRole("button", { name: "Daha fazla göster" }));
    await waitFor(() => expect(screen.getAllByTestId("metric-item")).toHaveLength(3));
    expect(screen.queryByRole("button", { name: "Daha fazla göster" })).toBeNull();
    expect(screen.getByTestId("metric-count")).toHaveTextContent("Toplam: 3");
  });

  it("shows the shortcut to the screen where the report has one, and minutes for the median", async () => {
    const approvals = `${REPORT_BASE}/${YESTERDAY}/metrics/pending_approvals_now`;
    mockApi(
      routes({
        [`GET ${approvals}`]: () => json(metricItems("pending_approvals_now", 1, [item(1, { kind: "approval" })])),
        [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      }),
    );
    renderApp(`${REPORT_URL}/${YESTERDAY}/pending_approvals_now`);
    expect(await screen.findByRole("link", { name: "Ekranda aç" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/approvals`);
  });

  it("shows each answered burst with its minutes for the median", async () => {
    const median = `${REPORT_BASE}/${YESTERDAY}/metrics/median_first_response_minutes`;
    mockApi(
      routes({
        [`GET ${median}`]: () =>
          json(metricItems("median_first_response_minutes", 6.5, [item(1, { measure: 5 }), item(2, { measure: 8 })])),
        [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      }),
    );
    renderApp(`${REPORT_URL}/${YESTERDAY}/median_first_response_minutes`);
    expect(await screen.findByTestId("metric-count")).toHaveTextContent("Ortanca süre: 6,5 dk");
    const rows = screen.getAllByTestId("metric-item");
    expect(nth(rows, 0)).toHaveTextContent("5 dk");
    expect(nth(rows, 1)).toHaveTextContent("8 dk");
  });

  it("explains a number with nothing behind it", async () => {
    mockApi(
      routes({
        [`GET ${DRILL}`]: () => json(metricItems("inbound_messages", 0, [])),
        [`GET ${REPORT_BASE}`]: () => json(report(YESTERDAY)),
      }),
    );
    renderApp(ROUTE);
    expect(await screen.findByText("Bu sayının arkasında kayıt yok")).toBeInTheDocument();
  });

  it("is a not-found page for a malformed day", async () => {
    mockApi(routes());
    renderApp(`${REPORT_URL}/not-a-day/inbound_messages`);
    await waitFor(() => expect(screen.queryByTestId("metric-count")).toBeNull());
    expect(screen.queryByRole("heading", { name: "Gelen mesaj" })).toBeNull();
  });
});
