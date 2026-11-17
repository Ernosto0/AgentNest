import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { ME, READINESS, WS_GOLKENT, candidate, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const ACCOUNT = "a1000000-0000-4000-8000-000000000001";
const Q = "a2000000-0000-4000-8000-000000000001";
const CANDIDATE = "c0000000-0000-4000-8000-0000000000aa";
const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const AP = `${BASE}/accounts/${ACCOUNT}`;

afterEach(() => vi.unstubAllGlobals());

const answer = (extra: Record<string, unknown> = {}) => ({
  id: "ans1",
  question_id: Q,
  version: 4,
  kind: "answer",
  body: "Children under six train free.",
  author_role: "owner",
  candidate_id: CANDIDATE,
  candidate_status: "pending",
  candidate_editor_type: null,
  expires_at: "2027-01-01T00:00:00Z",
  ...extra,
});

function setup(role: string, answers: () => Response, extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    "GET /api/v1/meta": () =>
      json({
        product_name: "AgentNest",
        demo_tools_enabled: true,
        llm_mode: "fake",
        supported_locales: ["tr", "en"],
        instagram_providers: ["mock"],
      }),
    "GET /api/v1/auth/me": () =>
      json({
        ...ME,
        user: { ...ME.user, ui_locale: "en" },
        memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
      }),
    [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/social-accounts`]: () =>
      json({
        items: [
          {
            id: ACCOUNT,
            username: "business",
            status: "connected",
            provider_kind: "mock",
            platform: "instagram",
            capabilities: {},
            is_simulated: true,
          },
        ],
        next_cursor: null,
      }),
    [`GET ${AP}/owner-questions`]: () => json({ items: [], next_cursor: null }),
    [`GET ${AP}/owner-questions/${Q}`]: () =>
      json({
        id: Q,
        thread_id: "t1",
        customer_id: "customer1",
        source_cursor: 2,
        required_info: "exception",
        visibility: "customer_reply",
        body: "Do children train free?",
        state: "answered",
        version: 4,
        answer_id: "ans1",
        expires_at: "2027-01-01T00:00:00Z",
      }),
    [`GET ${AP}/owner-questions/${Q}/answers`]: answers,
    ...extra,
  });
}

async function openQuestion() {
  await i18n.changeLanguage("en");
  return renderApp(`/w/${WS_GOLKENT}/more/agent/questions/${Q}?account=${ACCOUNT}`);
}

describe("save an owner answer as a verified fact", () => {
  it("offers one tap, accepts the candidate through the existing endpoint and then confirms", async () => {
    let saved = false;
    const requests = setup(
      "owner",
      () => json({ items: [answer({ candidate_status: saved ? "accepted" : "pending" })], next_cursor: null }),
      {
        [`POST ${BASE}/fact-candidates/${CANDIDATE}/accept`]: () => {
          saved = true;
          return json({ kind: "fact", id: "f1", key: "custom.owner_answer_x" });
        },
      },
    );
    await openQuestion();
    const offer = await screen.findByTestId("save-as-fact");
    expect(within(offer).getByText("Save this as a verified fact?")).toBeVisible();
    // Nothing is sent just by showing the offer or by typing free text elsewhere.
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(0);
    await userEvent.click(within(offer).getByRole("button", { name: "Save as verified fact" }));
    await waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1));
    const post = requests.find((r) => r.method === "POST")!;
    expect(post.path).toBe(`${BASE}/fact-candidates/${CANDIDATE}/accept`);
    expect(post.body ?? null).toBeNull(); // no typed value: the plain-text answer is saved as is
    expect(await screen.findByText(/Saved as a verified fact/)).toBeVisible();
    expect(screen.queryByTestId("save-as-fact")).toBeNull();
  });

  it("sends an answer with a price to the typed editor instead of a one-tap save", async () => {
    const requests = setup("owner", () =>
      json({ items: [answer({ candidate_editor_type: "money" })], next_cursor: null }),
    );
    await openQuestion();
    const offer = await screen.findByTestId("save-as-fact");
    expect(within(offer).queryByRole("button", { name: "Save as verified fact" })).toBeNull();
    expect(within(offer).getByRole("link", { name: "Review in Suggestions" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/knowledge/suggestions`,
    );
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(0);
  });

  it("shows no offer for a rejected or missing candidate, and none for staff", async () => {
    setup("owner", () => json({ items: [answer({ candidate_status: "rejected" })], next_cursor: null }));
    const { unmount } = await openQuestion();
    await screen.findByText("Answer history");
    expect(screen.queryByTestId("save-as-fact")).toBeNull();
    unmount();
    setup("staff", () => json({ items: [answer()], next_cursor: null }));
    await openQuestion();
    await screen.findByText("Answer history");
    expect(screen.queryByTestId("save-as-fact")).toBeNull();
  });
});

describe("typed save in Suggestions", () => {
  it("never offers a plain accept for an answer with a phone number and sends the typed value", async () => {
    await i18n.changeLanguage("en");
    const owner = candidate({
      id: CANDIDATE,
      fact_key: "custom.owner_answer_x",
      fact_id: null,
      value_type: "text",
      proposed_value: { text: "Call 0532 123 45 67 for lessons." },
      proposed_display: "Call 0532 123 45 67 for lessons.",
      current_display: null,
      relation: "new",
      source_type: "owner_answer",
      source_excerpt: null,
      editor_type: "phone",
    });
    const requests = mockApi({
      "GET /api/v1/meta": () =>
        json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"] }),
      "GET /api/v1/auth/me": () => json({ ...ME, user: { ...ME.user, ui_locale: "en" } }),
      [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT)),
      [`GET ${BASE}/readiness`]: () => json(READINESS),
      [`GET ${BASE}/facts`]: () => json({ items: [], next_cursor: null }),
      [`GET ${BASE}/facts/template`]: () => json([]),
      [`GET ${BASE}/fact-candidates`]: () => json({ items: [owner], next_cursor: null }),
      [`POST ${BASE}/fact-candidates/${CANDIDATE}/accept`]: () => json({ kind: "fact", id: "f1" }),
    });
    renderApp(`/w/${WS_GOLKENT}/more/knowledge/suggestions`);
    const card = await screen.findByTestId("candidate-custom.owner_answer_x");
    expect(within(card).queryByRole("button", { name: /^Use / })).toBeNull();
    const save = within(card).getByRole("button", { name: "Save as verified fact" });
    expect(save).toBeDisabled();
    await userEvent.type(within(card).getByLabelText("Phone number"), "0532 123 45 67");
    await userEvent.click(save);
    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(requests.find((r) => r.method === "POST")?.body).toMatchObject({
      value_type: "phone",
      value: { e164: expect.stringMatching(/^\+90532/) },
    });
  });
});

describe("learned this month on the Assistant page", () => {
  const agent = `${AP}/agent`;
  const overview = {
    state: "active",
    controller_mode: "agent",
    config_version: 3,
    controller_epoch: 2,
    is_simulated: true,
    session_counts: {},
    pending_questions: 0,
    pending_approvals: 0,
    recent_actions: [],
  };
  const page = (month: unknown) =>
    setup("owner", () => json({ items: [], next_cursor: null }), {
      [`GET ${agent}`]: () => json(overview),
      [`GET ${agent}/tasks`]: () => json({ items: [], next_cursor: null }),
      [`GET ${agent}/personality`]: () => json({ version: 1, goals: "", personality: {} }),
      [`GET ${agent}/delegation`]: () => json(null),
      [`GET ${BASE}/learning/month`]: () => json(month),
    });

  it("shows the count and a link to each fact", async () => {
    await i18n.changeLanguage("en");
    const requests = page({
      month: "2026-11",
      count: 2,
      items: [
        { fact_id: "f1", key: "custom.owner_answer_a", category: "custom", label: { tr: "Çocuklar ücretsiz", en: "Children train free" }, value_type: "text", learned_at: "2026-11-10T10:00:00Z" },
        { fact_id: "f2", key: "custom.owner_answer_b", category: "custom", label: { tr: "Havlu", en: "Towels included" }, value_type: "text", learned_at: "2026-11-09T10:00:00Z" },
      ],
    });
    renderApp(`/w/${WS_GOLKENT}/more/agent`);
    const card = await screen.findByTestId("agent-learned");
    expect(await within(card).findByText("Learned 2 things from you this month")).toBeVisible();
    expect(within(card).getByRole("link", { name: /Children train free/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/knowledge/custom#fact-custom.owner_answer_a`,
    );
    expect(within(card).getByRole("link", { name: /Towels included/ })).toBeVisible();
    expect(requests.some((r) => r.path.endsWith("/learning/month"))).toBe(true);
  });

  it("says so when nothing was learned yet this month", async () => {
    await i18n.changeLanguage("en");
    page({ month: "2026-11", count: 0, items: [] });
    renderApp(`/w/${WS_GOLKENT}/more/agent`);
    const card = await screen.findByTestId("agent-learned");
    expect(await within(card).findByText(/Nothing yet this month/)).toBeVisible();
    expect(within(card).queryByRole("link")).toBeNull();
  });
});
