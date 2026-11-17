import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { BASE } from "@/test/aiFixtures";
import { socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const ACCOUNT = "a1000000-0000-4000-8000-000000000001";
const SUGGESTION = "b2000000-0000-4000-8000-000000000002";
const base = `/api/v1/workspaces/${WS_GOLKENT}`;
const LIST = `GET ${base}/delegation-suggestions`;
const PREVIEW = `POST ${base}/accounts/${ACCOUNT}/agent/delegation/preview`;
const APPLY = `POST ${base}/accounts/${ACCOUNT}/agent/delegation/apply`;
const DISMISS = `POST ${base}/delegation-suggestions/${SUGGESTION}/dismiss`;

const CHANGE = {
  expected_config_version: 3,
  expected_delegation_version: null,
  client_request_id: SUGGESTION,
  suggestion_id: SUGGESTION,
  policy: { actions: { "dm.send": { mode: "off", sources: ["customer", "owner_task"], max_per_day: null } } },
};
const suggestion = (overrides = {}) => ({
  id: SUGGESTION,
  account_id: ACCOUNT,
  intent: "hours",
  action_class: "reply.hours",
  counts: { unchanged: 23, edited: 0, rejected: 0, failed: 0 },
  window_days: 28,
  expires_at: "2026-11-23T09:00:00Z",
  change: CHANGE,
  ...overrides,
});

const AGENT = `${base}/accounts/${ACCOUNT}/agent`;
const legacyAgent = {
  [`GET ${AGENT}`]: () =>
    json({ state: "inactive", controller_mode: "legacy", config_version: 3, controller_epoch: 2, is_simulated: false, session_counts: {}, pending_questions: 0, pending_approvals: 0, recent_actions: [] }),
  [`GET ${AGENT}/delegation`]: () => json(null),
  [`GET ${AGENT}/personality`]: () => json({ version: 1, goals: "", personality: {} }),
  [`GET ${AGENT}/tasks`]: () => json({ items: [], next_cursor: null }),
};

function setup(role = "owner", extra: Record<string, (r: RecordedRequest) => Response> = {}) {
  const me = {
    ...ME,
    user: { ...ME.user, ui_locale: "en" },
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
  };
  return mockApi({
    "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"] }),
    "GET /api/v1/auth/me": () => json(me),
    [`GET ${base}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: [socialAccount({ id: ACCOUNT })], next_cursor: null }),
    [LIST]: () => json({ items: [suggestion()] }),
    ...extra,
  });
}

async function open(path = "") {
  await i18n.changeLanguage("en");
  renderApp(`/w/${WS_GOLKENT}${path}`);
}

describe("approval ladder suggestion card (D-02)", () => {
  it("shows the evidence on Today and changes nothing until the owner reviews and confirms", async () => {
    const requests = setup("owner", {
      [PREVIEW]: () => json({ next_version: 1, changed_actions: [], automation_class: "reply.hours" }),
      [APPLY]: () => json({ id: "d1", version: 1, policy: CHANGE.policy, config_version: 4, controller_epoch: 3 }),
    });
    await open();
    const card = await screen.findByTestId("ladder-card");
    expect(within(card).getByRole("heading", { name: "Send replies about opening hours automatically?" })).toBeVisible();
    expect(card).toHaveTextContent("23 replies about opening hours");
    expect(card).toHaveTextContent("last 28 days");
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(0);

    await userEvent.click(within(card).getByRole("button", { name: "Review" }));
    await within(card).findByRole("button", { name: "Turn on automatic replies" });
    expect(requests.filter((r) => r.path.endsWith("/apply"))).toHaveLength(0);

    await userEvent.click(within(card).getByRole("button", { name: "Turn on automatic replies" }));
    await waitFor(() => expect(requests.filter((r) => r.path.endsWith("/apply"))).toHaveLength(1));
    const preview = requests.find((r) => r.path.endsWith("/delegation/preview"));
    const applied = requests.find((r) => r.path.endsWith("/delegation/apply"));
    expect(preview?.body).toEqual(CHANGE); // the server's own proposal, untouched
    expect(applied?.body).toEqual(preview?.body); // the same change that was previewed
    expect(await screen.findByTestId("ladder-done")).toHaveTextContent("Automatic replies about opening hours are on.");
  });

  it("can step back from the review without applying anything", async () => {
    const requests = setup("owner", { [PREVIEW]: () => json({ next_version: 1, changed_actions: [], automation_class: "reply.hours" }) });
    await open();
    const card = await screen.findByTestId("ladder-card");
    await userEvent.click(within(card).getByRole("button", { name: "Review" }));
    await userEvent.click(await within(card).findByRole("button", { name: "Back" }));
    expect(within(card).getByRole("button", { name: "Review" })).toBeVisible();
    expect(requests.filter((r) => r.path.endsWith("/apply"))).toHaveLength(0);
  });

  it("dismisses with Not now, records it and hides the card", async () => {
    let dismissed = false;
    const requests = setup("owner", {
      [LIST]: () => json({ items: dismissed ? [] : [suggestion()] }),
      [DISMISS]: () => {
        dismissed = true;
        return json({ id: SUGGESTION, status: "dismissed", cooldown_until: "2026-12-16T09:00:00Z" });
      },
    });
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "Not now" }));
    await waitFor(() => expect(screen.queryByTestId("ladder-card")).not.toBeInTheDocument());
    expect(requests.filter((r) => r.path.endsWith("/dismiss"))).toHaveLength(1);
    expect(requests.filter((r) => r.path.endsWith("/apply"))).toHaveLength(0);
  });

  it("shows a refusal and keeps the card when the suggestion no longer holds", async () => {
    setup("owner", { [PREVIEW]: () => problem(409, "CONFLICT_STATE", { params: { reason: "suggestion_ineligible" } }) });
    await open();
    const card = await screen.findByTestId("ladder-card");
    await userEvent.click(within(card).getByRole("button", { name: "Review" }));
    expect(await within(card).findByRole("alert")).toBeVisible();
    expect(within(card).getByRole("button", { name: "Review" })).toBeVisible();
  });

  it("is also on the Assistant page for that account", async () => {
    setup("owner", legacyAgent);
    await open("/more/agent");
    expect(await screen.findByTestId("ladder-card")).toBeVisible();
  });

  it("is not shown on the Assistant page for a suggestion about another account", async () => {
    setup("owner", {
      ...legacyAgent,
      [LIST]: () => json({ items: [suggestion({ account_id: "a1000000-0000-4000-8000-0000000000ff" })] }),
    });
    await open("/more/agent");
    await screen.findByRole("heading", { name: "Account assistant" });
    await waitFor(() => expect(screen.queryByTestId("ladder-card")).not.toBeInTheDocument());
  });

  it.each(["manager", "staff"])("is never requested or shown for a %s", async (role) => {
    const requests = setup(role);
    await open();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByTestId("ladder-card")).not.toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/delegation-suggestions"))).toHaveLength(0);
  });

  it("describes and links the weekly notification in both languages", async () => {
    const { describeNotification } = await import("@/features/notifications/describe");
    const { notificationTarget } = await import("@/features/notifications/target");
    const notification = {
      id: "n1",
      type: "delegation_suggestion",
      severity: "info",
      params: { account_id: ACCOUNT, intent: "hours" },
      read_at: null,
      created_at: "2026-11-16T09:00:00Z",
      is_simulated: false,
    } as never;
    await i18n.changeLanguage("en");
    expect(describeNotification(i18n.t.bind(i18n), notification, "en")).toBe("Your assistant has a suggestion: send some replies automatically");
    expect(notificationTarget(WS_GOLKENT, notification)).toBe(`/w/${WS_GOLKENT}/more/agent?account=${ACCOUNT}`);
    await i18n.changeLanguage("tr");
    expect(describeNotification(i18n.t.bind(i18n), notification, "tr")).toContain("öneri");
    await i18n.changeLanguage("en");
  });
});
