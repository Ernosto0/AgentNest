import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LeadList } from "@/api/types";
import i18n from "@/i18n";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { report } from "@/test/reportFixtures";
import { renderApp } from "@/test/renderApp";
import { shiftDay, todayIn } from "./dates";

const TODAY = todayIn("Europe/Istanbul");
const BASE = `/api/v1/workspaces/${WS_GOLKENT}/leads`;
const PAGE = `/w/${WS_GOLKENT}/more/reports/leads`;
type Handler = (r: RecordedRequest) => Response | Promise<Response>;

function routes(extra: Record<string, Handler> = {}, role: "owner" | "manager" | "staff" = "owner") {
  return {
    "GET /api/v1/meta": () => json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json({ ...ME, memberships: ME.memberships.map((m) => m.workspace_id === WS_GOLKENT ? { ...m, role } : m) }),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/reports/daily`]: () => json(report(TODAY)),
    [`GET ${BASE}`]: () => json(leads()),
    ...extra,
  };
}

function leads(overrides: Partial<LeadList> = {}): LeadList {
  return {
    period_from: shiftDay(TODAY, -29), period_to: TODAY, timezone: "Europe/Istanbul",
    total: 1, limit: 50, offset: 0, has_simulated_data: false,
    items: [{ conversation_id: "lead-1", customer_handle: "ayşe", last_question: "Fiyat nedir?",
      last_question_at: "2026-03-09T21:30:00Z", intent: "pricing",
      link: { api: null, route: `/w/${WS_GOLKENT}/inbox/lead-1` } }],
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("call-back list", () => {
  it("renders handle, workspace-local date, intent, question, links and safety notes", async () => {
    mockApi(routes());
    renderApp(PAGE);
    expect(await screen.findByText("ayşe")).toBeInTheDocument();
    expect(screen.getByText("Fiyat nedir?")).toBeInTheDocument();
    expect(screen.getByText("Fiyat")).toBeInTheDocument();
    expect(screen.getByText(new Date("2026-03-09T21:30:00Z").toLocaleString("tr", {
      dateStyle: "short", timeStyle: "short", timeZone: "Europe/Istanbul",
    }))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Konuşmayı aç" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/inbox/lead-1`);
    expect(screen.getByRole("link", { name: "Günlük rapora dön" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/reports`);
    expect(screen.getByText(/bir CRM değildir/)).toBeInTheDocument();
    expect(screen.getByText(/KVKK/)).toHaveTextContent(/Güvenli saklayın/);
    expect(screen.getByText(/fiyat bilgisine referans veren/)).toBeInTheDocument();
    expect(screen.getByText(i18n.t("reports.missed.simulatedNote"))).toBeInTheDocument();
  });

  it("refetches inclusive local periods for all three buttons", async () => {
    const requests = mockApi(routes());
    renderApp(PAGE);
    await screen.findByText("ayşe");
    const check = (days: number) => {
      const req = requests.filter((r) => r.path === BASE).at(-1)!;
      expect(new URLSearchParams(req.search).get("from")).toBe(shiftDay(TODAY, 1 - days));
      expect(new URLSearchParams(req.search).get("to")).toBe(TODAY);
    };
    check(30);
    const user = userEvent.setup();
    for (const days of [7, 90, 30]) {
      await user.click(screen.getByRole("button", { name: `Son ${days} gün` }));
      await waitFor(() => check(days));
      expect(screen.getByRole("button", { name: `Son ${days} gün` })).toHaveAttribute("aria-pressed", "true");
    }
  });

  it("renders empty state and disables export", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => json(leads({ items: [], total: 0 })) }));
    renderApp(PAGE);
    expect(await screen.findByText("Geri aranacak müşteri yok")).toBeInTheDocument();
    screen.getAllByRole("button", { name: "CSV indir" }).forEach((b) => expect(b).toBeDisabled());
  });

  it("renders nullable handle/text and booking label", async () => {
    const data = leads();
    data.items[0] = { ...data.items[0]!, customer_handle: null, last_question: null, intent: "booking" };
    mockApi(routes({ [`GET ${BASE}`]: () => json(data) }));
    renderApp(PAGE);
    expect(await screen.findByText("Müşteri")).toBeInTheDocument();
    expect(screen.getByText("Metin yok (sesli mesaj veya silinmiş)")).toBeInTheDocument();
    expect(screen.getByText("Randevu")).toBeInTheDocument();
  });

  it("loads the next page using offset without replacing earlier cards", async () => {
    const requests = mockApi(routes({ [`GET ${BASE}`]: (r) => {
      const offset = Number(new URLSearchParams(r.search).get("offset"));
      const data = leads({ total: 2, offset });
      if (offset) data.items[0] = { ...data.items[0]!, conversation_id: "lead-2", customer_handle: "mehmet" };
      return json(data);
    } }));
    renderApp(PAGE);
    await screen.findByText("ayşe");
    await userEvent.setup().click(screen.getByRole("button", { name: "Daha fazla yükle" }));
    expect(await screen.findByText("mehmet")).toBeInTheDocument();
    expect(screen.getByText("ayşe")).toBeInTheDocument();
    expect(new URLSearchParams(requests.filter((r) => r.path === BASE).at(-1)!.search).get("offset")).toBe("1");
  });

  it("exports the selected period and confirms only after the blob has arrived", async () => {
    let finishBlob!: (value: Blob) => void;
    const received = new Promise<Blob>((resolve) => { finishBlob = resolve; });
    const response = new Response("csv", { headers: { "content-type": "text/csv", "X-Row-Count": "3", "X-Truncated": "true" } });
    vi.spyOn(response, "blob").mockReturnValue(received);
    const requests = mockApi(routes({ [`POST ${BASE}/export`]: () => response }));
    const create = vi.fn(() => "blob:leads");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderApp(PAGE);
    await screen.findByText("ayşe");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Son 7 gün" }));
    await user.click(screen.getAllByRole("button", { name: "CSV indir" })[0]!);
    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(create).not.toHaveBeenCalled();
    expect(screen.queryByText(/satır dışa aktarıldı/)).not.toBeInTheDocument();
    const blob = new Blob(["\ufeffcustomer_handle,last_question,date,conversation_link\r\n"]);
    await act(async () => { finishBlob(blob); });
    expect(await screen.findByText(/3 satır dışa aktarıldı/)).toBeInTheDocument();
    expect(screen.getByText(/5.000 satır sınırına/)).toBeInTheDocument();
    const post = requests.find((r) => r.method === "POST")!;
    expect(post.body).toEqual({ from: shiftDay(TODAY, -6), to: TODAY });
    expect(create).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:leads");
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it("uses the list total when the row-count header is not readable", async () => {
    mockApi(routes({ [`POST ${BASE}/export`]: () => new Response("csv") }));
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:leads") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderApp(PAGE);
    await screen.findByText("ayşe");
    await userEvent.setup().click(screen.getAllByRole("button", { name: "CSV indir" })[0]!);
    expect(await screen.findByText("1 satır dışa aktarıldı")).toBeInTheDocument();
  });

  it("shows list errors through ErrorMessage", async () => {
    mockApi(routes({ [`GET ${BASE}`]: () => problem(403, "FORBIDDEN") }));
    renderApp(PAGE);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/satır dışa aktarıldı/)).not.toBeInTheDocument();
  });

  it("shows export errors without a success confirmation", async () => {
    mockApi(routes({ [`POST ${BASE}/export`]: () => problem(403, "FORBIDDEN") }));
    renderApp(PAGE);
    await screen.findByText("ayşe");
    await userEvent.setup().click(screen.getAllByRole("button", { name: "CSV indir" })[0]!);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/satır dışa aktarıldı/)).not.toBeInTheDocument();
  });

  it("shows not found to staff without requesting lead data", async () => {
    const requests = mockApi(routes({}, "staff"));
    renderApp(PAGE);
    expect(await screen.findByText(i18n.t("notFound.title"))).toBeInTheDocument();
    expect(requests.some((r) => r.path === BASE)).toBe(false);
  });

  it("hides the daily report link from staff", async () => {
    mockApi(routes({}, "staff"));
    renderApp(`/w/${WS_GOLKENT}/more/reports`);
    await screen.findByRole("heading", { name: i18n.t("reports.title") });
    expect(screen.queryByTestId("leads-report-link")).not.toBeInTheDocument();
  });

  it("links the daily report to the list for managers", async () => {
    mockApi(routes({}, "manager"));
    renderApp(`/w/${WS_GOLKENT}/more/reports`);
    expect(await screen.findByTestId("leads-report-link")).toHaveAttribute("href", PAGE);
  });
});
