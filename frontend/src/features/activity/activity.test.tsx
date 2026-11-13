import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActivitySummary } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
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

const SUMMARY: ActivitySummary = {
  days: 7,
  period_start: "2026-10-08T21:00:00Z",
  period_end: "2026-10-15T12:00:00Z",
  total: 42,
  routine: 120,
  failure: 2,
  warning: 5,
  success: 30,
};

function routes(extra: Record<string, () => Response> = {}, me = ME) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
    [`GET ${ACTIVITY_PATH}/summary`]: () => json(SUMMARY),
    ...extra,
  };
}

const page = (items: ReturnType<typeof entry>[], next_cursor: string | null = null) => ({ items, next_cursor });
const activityRequests = (requests: { path: string; search: string }[]) => requests.filter((r) => r.path === ACTIVITY_PATH);

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
                level: "info",
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
    expect(within(nth(rows, 0)).getByText("Demo Sahip")).toBeInTheDocument();
    expect(within(nth(rows, 0)).getByText("15:00")).toBeInTheDocument();
    // 20:30 UTC is 23:30 in Istanbul, the workspace clock.
    expect(within(nth(rows, 1)).getByText("Bilgi güncellendi")).toBeInTheDocument();
    expect(within(nth(rows, 1)).getByText("Eski üye")).toBeInTheDocument();
    expect(within(nth(rows, 1)).getByText("23:30")).toBeInTheDocument();
    // No screen for the fact: its label is plain text, not a link.
    expect(within(nth(rows, 1)).queryByRole("link")).toBeNull();
    expect(within(nth(rows, 1)).getByText("Aylık üyelik")).toBeInTheDocument();
    // Only the simulated entry carries the badge (INV-09).
    expect(within(nth(rows, 0)).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(nth(rows, 1)).queryByTestId("simulated-badge")).toBeNull();
  });

  it("asks the server for key activity by default and for the chosen group", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(
            last.search.includes("type=messages")
              ? page([entry(3, { action: "message.received", group: "messages", text: "Mesaj alındı", level: "info" })])
              : page([entry(1), entry(2)]),
          );
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    expect(await screen.findAllByTestId("activity-entry")).toHaveLength(2);
    expect(nth(activityRequests(requests), 0).search).toContain("include_routine=false");
    const chip = screen.getByRole("button", { name: "Mesajlar" });
    expect(chip).toHaveAttribute("aria-pressed", "false");

    await userEvent.setup().click(chip);
    expect(await screen.findByText("Mesaj alındı")).toBeInTheDocument();
    expect(screen.getAllByTestId("activity-entry")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Mesajlar" })).toHaveAttribute("aria-pressed", "true");
    expect(activityRequests(requests).some((r) => r.search.includes("type=messages"))).toBe(true);
    expect(screen.getByTestId("activity-active-filters")).toHaveTextContent("Mesajlar");

    await userEvent.setup().click(screen.getByRole("button", { name: "Filtreleri temizle" }));
    await waitFor(() => expect(screen.getAllByTestId("activity-entry")).toHaveLength(2));
    expect(screen.queryByTestId("activity-active-filters")).toBeNull();
  });

  it("shows the server's summary and filters the feed by an outcome from it", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(
            last.search.includes("level=failure")
              ? page([entry(4, { action: "reply.failed", text: "Yanıt gönderilemedi", level: "failure" })])
              : page([entry(1), entry(2)]),
          );
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    const summary = await screen.findByTestId("activity-summary");
    expect(await within(summary).findByTestId("activity-summary-total")).toHaveTextContent("42");
    expect(within(summary).getByText("+120 teknik kayıt")).toBeInTheDocument();

    await userEvent.setup().click(within(summary).getByTestId("activity-summary-failure"));
    const failed = await screen.findByText("Yanıt gönderilemedi");
    expect(within(failed.closest("[data-testid=activity-entry]") as HTMLElement).getByText("Başarısız")).toBeInTheDocument();
    expect(within(summary).getByTestId("activity-summary-failure")).toHaveAttribute("aria-pressed", "true");
    expect(activityRequests(requests).some((r) => r.search.includes("level=failure") && !r.search.includes("level=warning"))).toBe(true);
    expect(screen.getByRole("combobox", { name: "Sonuç" })).toHaveValue("failure");

    await userEvent.setup().selectOptions(screen.getByRole("combobox", { name: "Sonuç" }), "problems");
    await waitFor(() =>
      expect(activityRequests(requests).some((r) => r.search.includes("level=failure") && r.search.includes("level=warning"))).toBe(true),
    );
  });

  it("turns technical entries on with one switch", async () => {
    const requests = mockApi(routes({ [`GET ${ACTIVITY_PATH}`]: () => json(page([entry(1)])) }));
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    await screen.findAllByTestId("activity-entry");
    const toggle = screen.getByRole("button", { name: "Teknik kayıtlar" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.setup().click(toggle);
    await waitFor(() => expect(activityRequests(requests).some((r) => r.search.includes("include_routine=true"))).toBe(true));
    expect(screen.getByRole("button", { name: "Teknik kayıtlar" })).toHaveAttribute("aria-pressed", "true");
  });

  it("folds repeated entries into one group that opens to every individual entry", async () => {
    const alerts = Array.from({ length: 5 }, (_, i) =>
      entry(i + 1, {
        action: "security.operator_alert_fired",
        group: "system",
        text: "Operatör uyarısı sürüyor: asistan oturumu 30 dakikadan uzun süredir ilerlemiyor",
        level: "warning",
        actor: { type: "system", label: "Sistem" },
        occurred_at: `2026-10-15T1${i}:00:00Z`,
        collapse_key: "alert-stuck",
        resource: null,
      }),
    ).reverse();
    mockApi(routes({ [`GET ${ACTIVITY_PATH}`]: () => json(page([...alerts, entry(8, { occurred_at: "2026-10-15T09:00:00Z" })])) }));
    renderApp(`/w/${WS_GOLKENT}/more/activity`);

    const group = await screen.findByTestId("activity-group");
    expect(within(group).getByText("5 kayıt")).toBeInTheDocument();
    expect(within(group).getByText("Benzer kayıtlar gruplandı")).toBeInTheDocument();
    expect(within(group).getByText("Uyarı")).toBeInTheDocument();
    // Only the ungrouped entry is a row until the group is opened.
    expect(screen.getAllByTestId("activity-entry")).toHaveLength(1);

    const toggle = within(group).getByRole("button", { expanded: false });
    await userEvent.setup().click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const inside = within(screen.getByRole("list", { name: "5 kayıt" })).getAllByTestId("activity-entry");
    expect(inside).toHaveLength(5);

    // Each grouped entry can still be inspected on its own.
    await userEvent.setup().click(within(nth(inside, 2)).getByRole("button", { expanded: false }));
    const details = within(nth(inside, 2)).getByTestId("activity-entry-details");
    expect(within(details).getByText("e0000000-0000-4000-8000-000000000003")).toBeInTheDocument();
  });

  it("shows an entry's details and its related flow", async () => {
    const flow = "f1000000-0000-4000-8000-000000000001";
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(
            last.search.includes(`correlation=${flow}`)
              ? page([entry(1, { correlation_id: flow }), entry(2, { action: "message.received", text: "Mesaj alındı", correlation_id: flow, level: "info" })])
              : page([
                  entry(1, {
                    correlation_id: flow,
                    details: [{ key: "error_code", label: "Neden kodu", value: "PROVIDER_RATE_LIMITED" }],
                  }),
                ]),
          );
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    const row = nth(await screen.findAllByTestId("activity-entry"), 0);
    await userEvent.setup().click(within(row).getByRole("button", { name: /Yanıt gönderildi/ }));
    const details = within(row).getByTestId("activity-entry-details");
    expect(within(details).getByText("Neden kodu")).toBeInTheDocument();
    expect(within(details).getByText("PROVIDER_RATE_LIMITED")).toBeInTheDocument();
    expect(within(details).getByText("Tamamlandı")).toBeInTheDocument();

    await userEvent.setup().click(within(details).getByRole("button", { name: "İlgili etkinliği göster" }));
    expect(await screen.findByTestId("activity-flow")).toBeInTheDocument();
    expect(await screen.findByText("Mesaj alındı")).toBeInTheDocument();
    const flowRequest = activityRequests(requests).find((r) => r.search.includes("correlation="));
    expect(flowRequest?.search).toContain("include_routine=true");
    expect(screen.queryByTestId("activity-filters")).toBeNull();

    await userEvent.setup().click(screen.getByRole("button", { name: "Tüm etkinliğe dön" }));
    expect(await screen.findByTestId("activity-filters")).toBeInTheDocument();
  });

  it("loads the next page with the cursor, keeps a run grouped across pages, then stops", async () => {
    const run = (n: number, hour: number) =>
      entry(n, { collapse_key: "same", text: "Gönderi düzenlendi", level: "info", occurred_at: `2026-10-15T${String(hour).padStart(2, "0")}:00:00Z` });
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          return json(last.search.includes("cursor=abc") ? page([run(4, 10), run(5, 9)]) : page([run(1, 13), run(2, 12), run(3, 11)], "abc"));
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    const group = await screen.findByTestId("activity-group");
    // The run reaches the end of what is loaded and more exists: the count is open-ended.
    expect(within(group).getByText("3+ kayıt")).toBeInTheDocument();
    expect(screen.getByText("3 kayıt gösteriliyor")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Daha eski etkinlikleri yükle" }));
    await waitFor(() => expect(within(screen.getByTestId("activity-group")).getByText("5 kayıt")).toBeInTheDocument());
    expect(screen.getAllByTestId("activity-group")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Daha eski etkinlikleri yükle" })).toBeNull();
    expect(screen.getByText("5 kayıt gösteriliyor · hepsi bu")).toBeInTheDocument();
  });

  it("offers a retry when an older page fails to load", async () => {
    let failNext = true;
    const requests = mockApi(
      routes({
        [`GET ${ACTIVITY_PATH}`]: () => {
          const last = requests.at(-1)!;
          if (last.search.includes("cursor=abc")) {
            if (failNext) {
              failNext = false;
              return problem(422, "VALIDATION_FAILED");
            }
            return json(page([entry(2, { occurred_at: "2026-10-15T10:00:00Z" })]));
          }
          return json(page([entry(1)], "abc"));
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    await screen.findAllByTestId("activity-entry");
    await userEvent.setup().click(screen.getByRole("button", { name: "Daha eski etkinlikleri yükle" }));
    const retry = await screen.findByRole("button", { name: "Yeniden dene" });
    // The loaded entries stay on screen.
    expect(screen.getAllByTestId("activity-entry")).toHaveLength(1);
    await userEvent.setup().click(retry);
    await waitFor(() => expect(screen.getAllByTestId("activity-entry")).toHaveLength(2));
  });

  it("explains an empty feed and an empty filter", async () => {
    mockApi(routes({ [`GET ${ACTIVITY_PATH}`]: () => json(page([])) }));
    renderApp(`/w/${WS_GOLKENT}/more/activity`);
    expect(await screen.findByText("Henüz etkinlik yok")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Teknik kayıtları göster" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Onaylar" }));
    expect(await screen.findByText("Bu filtrelere uyan kayıt yok")).toBeInTheDocument();
  });

  it("is in the More menu for the owner and not for staff", async () => {
    mockApi(routes());
    const owner = renderApp(`/w/${WS_GOLKENT}/more`);
    expect(await within(await screen.findByRole("main")).findByRole("link", { name: /Etkinlik/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/activity`,
    );
    expect(within(screen.getByRole("main")).getByRole("link", { name: /Günlük rapor/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/reports`,
    );
    owner.unmount();

    vi.unstubAllGlobals();
    mockApi(routes({}, STAFF_ME));
    renderApp(`/w/${WS_GOLKENT}/more`);
    expect(await within(await screen.findByRole("main")).findByRole("link", { name: /Günlük rapor/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Etkinlik/ })).toBeNull();
  });
});
