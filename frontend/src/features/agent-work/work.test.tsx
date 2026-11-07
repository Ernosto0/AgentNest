import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { mockApi, json, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
const ACCOUNT = "a1000000-0000-4000-8000-000000000001",
  Q = "a2000000-0000-4000-8000-000000000001",
  CUSTOMER = "customer1",
  BASE = `/api/v1/workspaces/${WS_GOLKENT}`,
  AP = `${BASE}/accounts/${ACCOUNT}`;
afterEach(() => vi.unstubAllGlobals());
function setup(role = "owner", extra: Parameters<typeof mockApi>[0] = {}) {
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
        memberships: ME.memberships.map((m) =>
          m.workspace_id === WS_GOLKENT ? { ...m, role } : m,
        ),
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
    [`GET ${AP}/agent/task-selections`]: () => json({ items: [], next_cursor: null }),
    [`GET ${AP}/comments/c1/moderation-operations`]: () => json({ items: [], next_cursor: null }),
    [`GET ${AP}/owner-questions/${Q}`]: () =>
      json({
        id: Q,
        thread_id: "t1",
        customer_id: CUSTOMER,
        source_cursor: 2,
        required_info: "exception",
        visibility: "customer_reply",
        body: "Can we make an exception?",
        state: "pending",
        version: 3,
        answer_id: null,
        expires_at: "2027-01-01T00:00:00Z",
      }),
    [`GET ${AP}/owner-questions/${Q}/answers`]: () => json({ items: [], next_cursor: null }),
    ...extra,
  });
}
async function open(path: string) {
  await i18n.changeLanguage("en");
  return renderApp(`/w/${WS_GOLKENT}/more/agent/${path}?account=${ACCOUNT}`);
}
describe("assistant work", () => {
  it("does not mount private question or memory views from a DM projection in a public route", async () => {
    const requests = setup("owner", {
      [`GET ${AP}/comments/threads/public-thread`]: () => json({ items: [], next_cursor: null }),
      [`GET ${AP}/agent/threads`]: () => json({ items: [{ id: "dm-thread", surface: "dm", source_ref: "public-thread", state: "active", handling_mode: "agent", version: 1, customer_id: CUSTOMER, goal: null, actions: [], is_simulated: true }], next_cursor: null }),
    });
    const { client } = await open("comments/public-thread");
    await screen.findByRole("heading", { name: "Public comment thread" });
    await waitFor(() => expect(client.getQueryData(["agent", WS_GOLKENT, ACCOUNT, "threads", "public-thread"])).toBeDefined());
    await waitFor(() => expect(client.isFetching()).toBe(0));
    expect(screen.queryByRole("link", { name: "Customer memory" })).toBeNull();
    expect(requests.some(r => r.path.includes("owner-questions") || r.path.includes("/memory"))).toBe(false);
  });
  it("answers information with version and idempotency, separately from approval", async () => {
    const requests = setup("owner", {
      [`POST ${AP}/owner-questions/${Q}/answer`]: () =>
        json({
          id: "answer",
          question_id: Q,
          version: 4,
          kind: "answer",
          body: "Yes",
          author_role: "owner",
          candidate_id: null,
          expires_at: "2027-01-01T00:00:00Z",
        }),
    });
    await open(`questions/${Q}`);
    await userEvent.type(await screen.findByLabelText("Business answer"), "Yes");
    await userEvent.click(screen.getByRole("button", { name: "Save information answer" }));
    await screen.findByText(/Information recorded/);
    const mutations = requests.filter((r) => r.method === "POST");
    expect(mutations).toHaveLength(1);
    expect(mutations[0]!.body).toMatchObject({
      expected_version: 3,
      kind: "answer",
      body: "Yes",
      reusable_knowledge: null,
    });
    expect((mutations[0]!.body as { client_request_id: string }).client_request_id).toMatch(
      /^[0-9a-f-]{36}$/,
    );
    expect(requests.some((r) => r.path.includes("/decision"))).toBe(false);
  });
  it("generates a stable valid knowledge key without asking the owner for one", async () => {
    const requests = setup("owner", { [`POST ${AP}/owner-questions/${Q}/answer`]: () => json({ id: "answer", question_id: Q, version: 4, kind: "answer", body: "Yes", author_role: "owner", candidate_id: "candidate", expires_at: "2027-01-01T00:00:00Z" }) });
    await open(`questions/${Q}`);
    await userEvent.type(await screen.findByLabelText("Business answer"), "Yes");
    await userEvent.click(screen.getByLabelText("Save for future answers"));
    expect(screen.queryByLabelText(/Knowledge key/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save information answer" }));
    await screen.findByText(/Information recorded/);
    expect(requests.find(r => r.method === "POST")?.body).toMatchObject({ reusable_knowledge: { key: "custom.owner_answer_a2000000000040008000000000000001", text: "Yes" } });
  });
  it("staff propose information and never see authoritative answer or reusable controls", async () => {
    setup("staff");
    await open(`questions/${Q}`);
    expect(await screen.findByLabelText("Your proposed answer")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Save information answer" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/knowledge candidate/)).not.toBeInTheDocument();
  });
  it("expired questions cannot be answered", async () => {
    setup("owner", {
      [`GET ${AP}/owner-questions/${Q}`]: () =>
        json({
          id: Q,
          customer_id: CUSTOMER,
          body: null,
          state: "expired",
          version: 4,
          visibility: "customer_reply",
          expires_at: "2026-01-01T00:00:00Z",
        }),
    });
    await open(`questions/${Q}`);
    expect(await screen.findByText("Expired")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Save information answer" }),
    ).not.toBeInTheDocument();
  });
  it("stale answer keeps text and exposes conflict without approving anything", async () => {
    setup("owner", {
      [`POST ${AP}/owner-questions/${Q}/answer`]: () => problem(409, "VERSION_CONFLICT"),
    });
    await open(`questions/${Q}`);
    await userEvent.type(await screen.findByLabelText("Business answer"), "My answer");
    await userEvent.click(screen.getByRole("button", { name: "Save information answer" }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByLabelText("Business answer")).toHaveValue("My answer");
  });
  it("memory forget clears private cached text and staff cannot correct", async () => {
    let forgotten = false;
    const requests = setup("manager", {
      [`GET ${AP}/customers/${CUSTOMER}/memory`]: () =>
        json({
          items: [
            {
              id: "m1",
              topic: "preference",
              kind: "preference",
              body: forgotten ? null : "Morning appointments",
              version: 1,
              expires_at: "2027-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/customers/${CUSTOMER}/sources`]: () => json({ items: [], next_cursor: null }),
      [`POST ${AP}/customers/${CUSTOMER}/memory/m1/forget`]: () => {
        forgotten = true;
        return json({ changed: true });
      },
    });
    await open(`memory/${CUSTOMER}`);
    await screen.findByText("Morning appointments");
    await userEvent.click(screen.getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(screen.queryByText("Morning appointments")).not.toBeInTheDocument());
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(1);
  });
  it("memory correction submits expected_version and new body", async () => {
    let currentBody = "Afternoon preferred";
    const requests = setup("owner", {
      [`GET ${AP}/customers/${CUSTOMER}/memory`]: () =>
        json({
          items: [
            {
              id: "m2",
              topic: "preference",
              kind: "preference",
              body: currentBody,
              version: 2,
              expires_at: "2027-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/customers/${CUSTOMER}/sources`]: () => json({ items: [], next_cursor: null }),
      [`POST ${AP}/customers/${CUSTOMER}/memory/m2/correct`]: () => {
        currentBody = "Evening only";
        return json({ changed: true });
      },
    });
    await open(`memory/${CUSTOMER}`);
    expect(await screen.findByText("Afternoon preferred")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Correct" }));

    const textarea = screen.getByLabelText("Corrected information");
    expect(textarea).toHaveValue("Afternoon preferred");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Evening only");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const correctPost = requests.find((r) => r.method === "POST" && r.path.includes("/correct"));
      expect(correctPost).toBeDefined();
      expect(correctPost?.body).toMatchObject({
        expected_version: 2,
        body: "Evening only",
      });
    });
  });
  it("memory correction conflict retains input and displays error", async () => {
    setup("owner", {
      [`GET ${AP}/customers/${CUSTOMER}/memory`]: () =>
        json({
          items: [
            {
              id: "m2",
              topic: "preference",
              kind: "preference",
              body: "Original text",
              version: 2,
              expires_at: "2027-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/customers/${CUSTOMER}/sources`]: () => json({ items: [], next_cursor: null }),
      [`POST ${AP}/customers/${CUSTOMER}/memory/m2/correct`]: () =>
        problem(409, "VERSION_CONFLICT"),
    });
    await open(`memory/${CUSTOMER}`);
    expect(await screen.findByText("Original text")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Correct" }));

    const textarea = screen.getByLabelText("Corrected information");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Conflicting edit");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByLabelText("Corrected information")).toHaveValue("Conflicting edit");
  });
  it("memory sources list shows observed timestamps and removed states", async () => {
    setup("owner", {
      [`GET ${AP}/customers/${CUSTOMER}/memory`]: () =>
        json({
          items: [
            {
              id: "m1",
              topic: "notes",
              kind: "notes",
              body: "Special equipment needed",
              version: 1,
              expires_at: "2027-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/customers/${CUSTOMER}/sources`]: () =>
        json({
          items: [
            {
              id: "s1",
              memory_id: "m1",
              removed: false,
              observed_at: "2026-10-20T10:00:00Z",
            },
            {
              id: "s2",
              memory_id: "m1",
              removed: true,
              observed_at: "2026-10-18T10:00:00Z",
            },
          ],
          next_cursor: null,
        }),
    });
    await open(`memory/${CUSTOMER}`);
    expect(await screen.findByText("Special equipment needed")).toBeVisible();
    expect(screen.getByText("Inspect sources")).toBeVisible();
    expect(screen.getByText("Customer private message")).toBeInTheDocument();
    expect(screen.getByText("Source removed")).toBeInTheDocument();
  });
  it("public thread loads no private memory or owner answers", async () => {
    const requests = setup("owner", {
      [`GET ${AP}/comments/threads/t1`]: () =>
        json({
          items: [
            {
              id: "c1",
              text: "Public question",
              state: "visible",
              thread_id: "t1",
              media_id: "media",
              is_owner: false,
              is_simulated: true,
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/agent/threads`]: () => json({ items: [], next_cursor: null }),
      [`GET ${AP}/comments/media/media`]: () =>
        json({
          id: "media",
          caption: "Post context",
          state: "visible",
          ownership_state: "verified_synthetic",
          version: 1,
          is_simulated: true,
        }),
    });
    await open("comments/t1");
    await screen.findByText("Public question");
    expect(
      requests.some((r) => r.path.includes("/customers/") || r.path.includes("owner-questions")),
    ).toBe(false);
  });
  it("unknown action remains checking and comment takeover carries version", async () => {
    const thread = {
      id: "t1",
      account_id: ACCOUNT,
      surface: "comment",
      source_ref: "t1",
      state: "waiting_operation",
      handling_mode: "agent",
      version: 8,
      customer_id: null,
      goal: "waiting_operation",
      is_simulated: true,
      actions: [
        {
          id: "a1",
          action_type: "comment.hide",
          status: "outcome_unknown",
          approval_id: null,
          operation_id: "op",
          outcome_code: null,
          is_simulated: true,
        },
      ],
    };
    const requests = setup("owner", {
      [`GET ${AP}/comments/threads/t1`]: () => json({ items: [], next_cursor: null }),
      [`GET ${AP}/agent/threads`]: () => json({ items: [thread], next_cursor: null }),
      [`POST ${AP}/agent/threads/t1/control`]: () =>
        json({ ...thread, handling_mode: "human", version: 9 }),
    });
    await open("comments/t1");
    expect(await screen.findByText(/Checking outcome; no repeat send/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Take over" }));
    await waitFor(() =>
      expect(requests.find((r) => r.method === "POST")?.body).toMatchObject({
        expected_version: 8,
        handling_mode: "human",
      }),
    );
  });
  it("comments list renders public notice, comment items, and links to thread", async () => {
    setup("owner", {
      [`GET ${AP}/comments`]: () =>
        json({
          items: [
            {
              id: "c-list-1",
              text: "How much does a membership cost?",
              state: "visible",
              thread_id: "thread-cost",
              media_id: "media-1",
              is_owner: false,
              is_simulated: true,
            },
          ],
          next_cursor: null,
        }),
    });
    await open("comments");
    expect(
      await screen.findByText(/Public surface. Private messages and customer memory are not loaded/),
    ).toBeVisible();
    const commentLink = await screen.findByRole("link", {
      name: "How much does a membership cost?",
    });
    expect(commentLink).toBeVisible();
    expect(commentLink.getAttribute("href")).toContain("/comments/thread-cost?account=");
    expect(screen.getByText("Customer comment")).toBeVisible();
    expect(screen.getByText("Visible")).toBeVisible();
  });
  it("manual moderation requires confirmation, sends expected_version and client_request_id", async () => {
    const requests = setup("owner", {
      [`GET ${AP}/comments/threads/t1`]: () =>
        json({
          items: [
            {
              id: "c1",
              text: "Inappropriate comment text",
              state: "visible",
              thread_id: "t1",
              media_id: "m1",
              version: 5,
              is_owner: false,
              is_simulated: true,
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/agent/threads`]: () => json({ items: [], next_cursor: null }),
      [`GET ${AP}/comments/media/m1`]: () =>
        json({
          id: "m1",
          caption: "Fitness workout session",
          state: "visible",
          ownership_state: "verified_synthetic",
          version: 1,
          is_simulated: true,
        }),
      [`POST ${AP}/comments/c1/moderate`]: () =>
        json({
          operation_id: "op-hide-1",
          status: "queued",
          effect: "hide",
          is_simulated: true,
        }),
    });
    await open("comments/t1");
    expect(await screen.findByText("Inappropriate comment text")).toBeVisible();
    expect(screen.getByText("Fitness workout session")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Hide comment" }));
    expect(
      screen.getByText(/This explicitly requests an effect on this exact comment version/),
    ).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Request this effect" }));
    await waitFor(() => {
      const modPost = requests.find((r) => r.method === "POST" && r.path.includes("/moderate"));
      expect(modPost).toBeDefined();
      expect(modPost?.body).toMatchObject({
        effect: "hide",
        expected_version: 5,
      });
      expect((modPost?.body as { client_request_id: string }).client_request_id).toMatch(
        /^[0-9a-f-]{36}$/,
      );
    });
  });
  it("staff members cannot moderate comments", async () => {
    setup("staff", {
      [`GET ${AP}/comments/threads/t1`]: () =>
        json({
          items: [
            {
              id: "c1",
              text: "Public comment for staff view",
              state: "visible",
              thread_id: "t1",
              media_id: "m1",
              version: 1,
              is_owner: false,
              is_simulated: true,
            },
          ],
          next_cursor: null,
        }),
      [`GET ${AP}/agent/threads`]: () => json({ items: [], next_cursor: null }),
      [`GET ${AP}/comments/media/m1`]: () =>
        json({
          id: "m1",
          caption: "Public post caption",
          state: "visible",
          ownership_state: "verified_synthetic",
          version: 1,
          is_simulated: true,
        }),
    });
    await open("comments/t1");
    expect(await screen.findByText("Public comment for staff view")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Hide comment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete comment" })).not.toBeInTheDocument();
  });
  it("resumable task clarification remains information and displays scheduled honestly", async () => {
    const requests = setup("owner", {
      [`GET ${AP}/agent/tasks/task1`]: () =>
        json({
          id: "task1",
          account_id: ACCOUNT,
          status: "waiting_owner",
          clarification: "Which image?",
          question_version: 2,
          actions: [
            {
              action_id: "a1",
              action_type: "content.schedule",
              status: "succeeded",
              content_id: "content1",
              content_status: "scheduled",
              is_simulated: true,
            },
          ],
        }),
      [`POST ${AP}/agent/tasks/task1/answers`]: () =>
        json({ id: "task1", status: "queued", actions: [] }),
    });
    await open("tasks/task1");
    await userEvent.type(
      await screen.findByLabelText("Provide the missing information"),
      "The selected image",
    );
    await userEvent.click(screen.getByRole("button", { name: "Submit information" }));
    await waitFor(() =>
      expect(requests.find((r) => r.method === "POST")?.body).toMatchObject({
        expected_version: 2,
        text: "The selected image",
      }),
    );
    expect(screen.getByText("Scheduled")).toBeVisible();
    expect(screen.queryByText("Published and verified")).not.toBeInTheDocument();
  });
});
import { approval, HASH } from "@/test/aiFixtures";

it.each([false, true])(
  "agent-action approvals load exact subject and disable stale previews (%s)",
  async (stale) => {
    const item = approval({
      id: "approval-agent",
      kind: "authorization",
      action: "comments.approve",
      subject: {
        type: "agent_action",
        id: "action1",
        version: 2,
        status: "waiting_approval",
        link: { target: "agent_action", id: "action1" },
      },
      summary: { action_type: "comment.hide" },
      is_simulated: true,
    });
    const requests = setup("owner", {
      [`GET ${BASE}/approvals`]: () => json({ items: [item], next_cursor: null }),
      [`GET ${BASE}/agent-actions/action1`]: () =>
        json({
          id: "action1",
          account_id: ACCOUNT,
          version: stale ? 3 : 2,
          payload_hash: HASH,
          status: "waiting_approval",
          action_type: "comment.hide",
          text: null,
          target_text: "Exact target comment",
          target_version: 1,
          content: null,
          is_simulated: true,
        }),
    });
    await i18n.changeLanguage("en");
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.click(await screen.findByRole("button", { name: /Review comment action/ }));
    expect(await screen.findByText("Exact target comment")).toBeVisible();
    expect(screen.getByRole("button", { name: "Approve" }).hasAttribute("disabled")).toBe(stale);
    expect(
      requests.some(
        (r) => r.path.includes("reply-drafts/action1") || r.path.includes("content-items/action1"),
      ),
    ).toBe(false);
  },
);
