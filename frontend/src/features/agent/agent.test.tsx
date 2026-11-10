import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { mockApi, json, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { ACTIONS } from "./hooks";
const ID = "a1000000-0000-4000-8000-000000000001", base = `/api/v1/workspaces/${WS_GOLKENT}`, agent = `${base}/accounts/${ID}/agent`;
const voice = { tone: "warm", formality: "professional", length: "short", emoji: "none", dm_style: "conversational", comment_style: "concise", examples: { tr: [], en: [] } };
afterEach(() => vi.unstubAllGlobals());
function setup(role = "owner", state = "active", mode = "agent", extra: Parameters<typeof mockApi>[0] = {}, connected = true) {
    const me = { ...ME, user: { ...ME.user, ui_locale: "en" }, memberships: ME.memberships.map(m => m.workspace_id === WS_GOLKENT ? { ...m, role } : m) };
    return mockApi({ "GET /api/v1/meta": () => json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"] }), "GET /api/v1/auth/me": () => json(me), [`GET ${base}`]: () => json(workspace(WS_GOLKENT)), [`GET ${base}/readiness`]: () => json(READINESS), [`GET ${base}/social-accounts`]: () => json({ items: [{ id: ID, username: "test", status: connected ? "connected" : "needs_reauth", platform: "instagram", provider_kind: "mock", capabilities: { messaging: true, comment_reply: false }, is_simulated: true }], next_cursor: null }), [`GET ${agent}`]: () => json({ state, controller_mode: mode, config_version: 3, controller_epoch: 2, is_simulated: true, session_counts: { waiting_owner: 1 }, pending_questions: 1, pending_approvals: 2, recent_actions: [{ id: "a", action_type: "dm.send", status: "outcome_unknown", operation_id: "o", created_at: "2026-10-29T12:00:00Z" }] }), [`GET ${agent}/personality`]: () => json({ version: 2, goals: "Help customers", personality: voice }), [`GET ${agent}/delegation`]: () => json(null), [`GET ${agent}/tasks`]: () => json({ items: [], next_cursor: null }), ...extra });
}
async function open(panel = "overview") { await i18n.changeLanguage("en"); renderApp(`/w/${WS_GOLKENT}/more/agent?panel=${panel}`); await screen.findByRole("heading", { name: "Account assistant" }); await screen.findByRole("heading", { name: panel === "voice" ? "Goals and voice" : panel === "permissions" ? "What the assistant may do" : panel === "history" ? "Recent actions" : "Your requests" }); }
describe("account assistant settings", () => {
    it("uses agent controls on the previous automation route after cutover", async () => {setup();await i18n.changeLanguage("en");renderApp(`/w/${WS_GOLKENT}/more/automation`);expect(await screen.findByRole("heading",{name:"Your requests"})).toBeVisible();expect(screen.queryByRole("heading",{name:"Reply automation"})).not.toBeInTheDocument();});
    it("shows owner control, honest unknown outcomes and a local preview with no network effect", async () => { const requests = setup(); await open(); expect(screen.getByText(/Checking outcome/)).toBeVisible(); expect(screen.getByText(/Already submitted or uncertain/)).toBeVisible(); await userEvent.click(screen.getByRole("link", { name: "Voice" })); const before = requests.length; await userEvent.click(screen.getByRole("button", { name: "Preview a sample conversation" })); expect(screen.getByText(/It does not run a model/)).toBeVisible(); expect(requests.slice(before).filter(r => r.method !== "GET")).toHaveLength(0); });
    it.each(["manager", "staff"])("enforces %s controls", async (role) => { setup(role); await open(); expect(screen.queryByRole("button", { name: "Pause assistant" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Preview permission changes" })).not.toBeInTheDocument(); await userEvent.click(screen.getByRole("link", { name: "Voice" })); expect(screen.queryByRole("button", { name: "Save goals and voice" }) !== null).toBe(role === "manager"); });
    it("does not apply delegation before a successful exact version preview", async () => { const requests = setup("owner", "active", "agent", { [`POST ${agent}/delegation/preview`]: () => json({ next_version: 1, changed_actions: ["dm.send"] }), [`POST ${agent}/delegation/apply`]: () => json({ version: 1, config_version: 4, controller_epoch: 3, policy: { actions: Object.fromEntries(ACTIONS.map(a => [a, { mode: "off", sources: ["customer", "owner_task"] }])) } }) }); await open("permissions"); const dm = within(screen.getByRole("group",{name:"Send direct messages"})); await userEvent.click(dm.getByRole("radio",{name:"Automatically"})); await userEvent.click(dm.getByText("Advanced settings")); await userEvent.type(dm.getByLabelText("Daily limit (blank: no additional limit)"),"3"); await userEvent.click(dm.getByLabelText("Customer interactions")); expect(screen.queryByRole("button", { name: "Apply these permissions" })).not.toBeInTheDocument(); await userEvent.click(screen.getByRole("button", { name: "Preview permission changes" })); await userEvent.click(await screen.findByRole("button", { name: "Apply these permissions" })); await waitFor(() => expect(requests.filter(r => r.path.endsWith("/delegation/apply"))).toHaveLength(1)); const preview = requests.find(r => r.path.endsWith("/delegation/preview")); expect(requests.find(r => r.path.endsWith("/delegation/apply"))?.body).toEqual(preview?.body); expect(preview?.body).toMatchObject({ expected_config_version: 3, expected_delegation_version: null, policy:{actions:{"dm.send":{mode:"automatic",max_per_day:3,sources:["owner_task"]}}} }); });
    it("retains edits and shows an error for a stale personality save", async () => { const requests = setup("owner", "active", "agent", { [`PATCH ${agent}/personality`]: () => problem(409, "VERSION_CONFLICT") }); await open("voice"); await userEvent.clear(screen.getByLabelText("Business goals")); await userEvent.type(screen.getByLabelText("Business goals"), "My goal"); await userEvent.click(screen.getByRole("button", { name: "Save goals and voice" })); expect(await screen.findByRole("alert")).toBeVisible(); expect(screen.getByLabelText("Business goals")).toHaveValue("My goal"); expect(requests.find(r => r.method === "PATCH")?.body).toMatchObject({ goals: "My goal", expected_version: 2 }); await userEvent.click(screen.getByRole("button",{name:"Discard edits and load current settings"})); await waitFor(()=>expect(screen.getByLabelText("Business goals")).toHaveValue("Help customers")); expect(screen.queryByRole("alert")).not.toBeInTheDocument(); });
    it("requires deliberate controller migration and uses backend version", async () => { const requests = setup("owner", "inactive", "legacy", { [`POST ${agent}/activate`]: () => json({ state: "active", controller_mode: "agent", config_version: 4, controller_epoch: 3 }) }); await open(); await userEvent.click(screen.getByRole("button", { name: "Enable account assistant" })); expect(requests.filter(r => r.method === "POST")).toHaveLength(0); await userEvent.click(screen.getByRole("button", { name: "Confirm control change" })); await waitFor(() => expect(requests.find(r => r.path.endsWith("/activate"))?.body).toMatchObject({ expected_config_version: 3, mode: "agent" })); });
    it("prevents resume on lost capability connection and labels unavailable capabilities", async () => { setup("owner", "paused", "agent", {}, false); await open(); expect(screen.getByRole("button", { name: "Resume assistant" })).toBeDisabled(); expect(screen.getByText(/Reconnect the account/)).toBeVisible(); expect(screen.getByText(/Unavailable/)).toBeVisible(); });
});

const CREATED = "2026-11-10T09:00:00Z";
const tasks = [
    { id: "t1", account_id: ID, source_channel: "telegram", status: "waiting_owner", outcome_code: null, created_at: CREATED, clarification: "Which class should the story promote?", question_version: 1, actions: [] },
    { id: "t2", account_id: ID, source_channel: "api", status: "completed", outcome_code: null, created_at: CREATED, clarification: null, question_version: null, actions: [{ action_id: "a", action_type: "content.prepare", status: "succeeded", content_id: "c1", content_status: "draft", is_simulated: true }] },
    { id: "t3", account_id: ID, source_channel: "api", status: "failed", outcome_code: null, created_at: CREATED, clarification: null, question_version: null, actions: [] },
];
describe("assistant control centre", () => {
    it("tracks requests by real state, links answers and content, and links actions to their request", async () => {
        setup("owner", "active", "agent", { [`GET ${agent}/tasks`]: () => json({ items: tasks, next_cursor: null }) });
        await open();
        const requests = within(screen.getByTestId("agent-requests"));
        expect(requests.getByText("Which class should the story promote?")).toBeVisible();
        expect(requests.getByRole("link", { name: "Answer" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/agent/tasks/t1?account=${ID}`);
        expect(requests.getByText(/via Telegram/)).toBeVisible();
        expect(requests.getByRole("link", { name: "Open content" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/content/c1`);
        expect(requests.getByRole("link", { name: /^Prepare image content/ })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/agent/tasks/t2?account=${ID}`);
        expect(within(screen.getByTestId("task-t3")).getByText("Failed")).toBeVisible();
        expect(within(screen.getByTestId("action-a")).getByRole("link", { name: "From your request" })).toBeVisible();
        expect(within(screen.getByTestId("agent-count-approvals")).getByText("2")).toBeVisible();
    });
    it("explains why a paused assistant cannot take requests and sends nothing", async () => {
        const requests = setup("owner", "paused");
        await open();
        expect(screen.getByText("Resume the assistant to send new requests.")).toBeVisible();
        await userEvent.type(screen.getByLabelText("Request"), "Prepare a post{Control>}{Enter}{/Control}");
        expect(screen.getByRole("button", { name: "Send request to assistant" })).toBeDisabled();
        expect(requests.filter(r => r.method === "POST")).toHaveLength(0);
    });
    it("sends a request with Ctrl+Enter and links to its progress", async () => {
        const requests = setup("owner", "active", "agent", { [`POST ${agent}/tasks`]: () => json({ ...tasks[1], id: "new", status: "queued", actions: [] }, 201) });
        await open();
        await userEvent.type(screen.getByLabelText("Request"), "Prepare a story{Control>}{Enter}{/Control}");
        await waitFor(() => expect(requests.find(r => r.method === "POST")?.body).toMatchObject({ text: "Prepare a story" }));
        expect(await screen.findByRole("link", { name: "Follow its progress" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/agent/tasks/new?account=${ID}`);
        expect(screen.getByLabelText("Request")).toHaveValue("");
    });
    it("groups capabilities and flags a permission the connection cannot use", async () => {
        const policy = { actions: Object.fromEntries(ACTIONS.map(a => [a, { mode: a === "comment.reply" ? "ask" : "off", sources: ["customer", "owner_task"] }])) };
        setup("owner", "active", "agent", { [`GET ${agent}/delegation`]: () => json({ id: "d", version: 1, policy, config_version: 3, controller_epoch: 2 }) });
        await open();
        const reply = within(screen.getByTestId("capability-comment_reply"));
        expect(reply.getByText("Reply publicly to comments")).toBeVisible();
        expect(reply.getByText("Asks first")).toBeVisible();
        expect(reply.getByText("Allowed, but the connection does not provide it.")).toBeVisible();
        expect(within(screen.getByRole("group", { name: "Comments" })).getByText("0/1")).toBeVisible();
    });
    it("filters history by what needs the owner", async () => {
        setup("owner", "active", "agent", { [`GET ${agent}/tasks`]: () => json({ items: tasks, next_cursor: null }) });
        await open("history");
        await userEvent.click(screen.getByRole("button", { name: /^Failed/ }));
        expect(screen.getByTestId("task-t3")).toBeVisible();
        expect(screen.queryByTestId("task-t1")).not.toBeInTheDocument();
        await userEvent.click(screen.getByRole("button", { name: /^Needs you/ }));
        expect(screen.getByTestId("task-t1")).toBeVisible();
        expect(screen.queryByTestId("task-t3")).not.toBeInTheDocument();
    });
});
