import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FactsUsed } from "@/components/FactsUsed";
import i18n from "@/i18n";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { buildSuggestions } from "./suggestions";
import type { TestChatDraft, TestChatState, TestChatTurn } from "./hooks";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
/** Pin "today" so a verification date from this year shows without its year. */
const pinToday = () => vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-15T10:00:00Z") });

const base = `/api/v1/workspaces/${WS_GOLKENT}`;
const chatPath = `${base}/assistant/test-chat`;
const META = { product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"] };

const draft = (overrides: Partial<TestChatDraft> = {}): TestChatDraft => ({
  text: "Monthly membership is 6.000 ₺ / month.",
  suggestion_text: null,
  decision: "approval_required",
  reasons: ["POLICY_REQUIRES_APPROVAL"],
  facts_used: [{ key: "pricing.membership_monthly", label: "Monthly membership", display: "6.000 ₺ / month", verified_at: "2026-10-12T09:00:00Z" }],
  language: "en",
  intent: "pricing_question",
  flags: [],
  ...overrides,
});
const turn = (overrides: Partial<TestChatTurn> = {}): TestChatTurn => ({
  id: "70000000-0000-4000-8000-000000000001",
  controller_mode: "legacy",
  status: "ready",
  customer_text: "How much is the monthly membership?",
  created_at: "2026-11-15T09:00:00Z",
  completed_at: "2026-11-15T09:00:02Z",
  draft: draft(),
  is_simulated: true,
  ...overrides,
});
const chat = (items: TestChatTurn[] = [], extra: Partial<TestChatState> = {}): TestChatState => ({
  controller_mode: "legacy",
  items,
  remaining_this_hour: 18,
  remaining_today: 55,
  ...extra,
});

const FACTS = [
  fact(),
  fact({ id: "f0000000-0000-4000-8000-000000000002", key: "pricing.student_monthly", label: { tr: "Öğrenci aylık üyelik", en: "Student membership" }, display: "4.000 ₺ / ay" }),
  fact({ id: "f0000000-0000-4000-8000-000000000003", key: "pricing.draft_only", label: { tr: "Taslak paket", en: "Draft package" }, status: "unverified", state: "unverified", usable: false }),
  fact({ id: "f0000000-0000-4000-8000-000000000004", key: "hours.weekdays", category: "hours", label: { tr: "Hafta içi saatleri", en: "Weekday hours" }, display: "09:00-21:00" }),
];

function setup(role = "owner", routes: Parameters<typeof mockApi>[0] = {}, facts = FACTS, locale: "tr" | "en" = "en") {
  const me = { ...ME, user: { ...ME.user, ui_locale: locale }, memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)) };
  return mockApi({
    "GET /api/v1/meta": () => json(META),
    "GET /api/v1/auth/me": () => json(me),
    [`GET ${base}`]: () => json(workspace(WS_GOLKENT, { default_locale: locale })),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/facts`]: () => json({ items: facts, next_cursor: null }),
    ...routes,
  });
}
async function open() {
  await i18n.changeLanguage("en");
  renderApp(`/w/${WS_GOLKENT}/more/agent/test`);
  await screen.findByRole("heading", { name: "Try your assistant", level: 1 });
}

describe("test chat screen", () => {
  it("starts with starter questions built from verified facts, and never states a value", async () => {
    setup("owner", { [`GET ${chatPath}`]: () => json(chat()) });
    await open();
    expect(await screen.findByText(/nothing here is sent to anyone/i)).toBeVisible();
    const list = await screen.findByTestId("suggestions");
    const questions = within(list).getAllByRole("button").map((b) => b.textContent ?? "");
    expect(questions.length).toBeGreaterThanOrEqual(4);
    expect(questions.length).toBeLessThanOrEqual(6);
    expect(questions).toContain("How much is Monthly membership?");
    expect(questions).toContain("What time are you open?");
    expect(questions.join(" ")).not.toMatch(/Draft package/); // an unverified fact is never used
    expect(questions.join(" ")).not.toMatch(/\d{2,}|₺/); // a question never states a price or an hour
    expect(screen.getByRole("button", { name: "Send test message" })).toBeDisabled();
  });

  it("sends a tapped question, polls while the reply is pending, then shows badge, decision, reason and facts", async () => {
    pinToday();
    let reads = 0;
    let sent = false;
    const requests = setup("owner", {
      [`GET ${chatPath}`]: () => {
        reads += 1;
        if (!sent) return json(chat());
        return json(chat([reads >= 3 ? turn() : turn({ status: "pending", draft: null, completed_at: null })], { remaining_this_hour: 17 }));
      },
      [`POST ${chatPath}/messages`]: () => {
        sent = true;
        return json(turn({ status: "pending", draft: null, completed_at: null }), 202);
      },
    });
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "How much is Monthly membership?" }));
    expect(await screen.findByText("Your assistant is writing…")).toBeVisible();
    const post = requests.find((r) => r.method === "POST");
    expect(post?.body).toEqual({ text: "How much is Monthly membership?" });
    expect(post?.headers.get("x-csrf-token")).toBe("csrf-token-for-tests");

    const reply = await screen.findByTestId("reply-text", undefined, { timeout: 5000 });
    expect(reply).toHaveTextContent("Monthly membership is 6.000 ₺ / month.");
    const bubble = screen.getByTestId("assistant-reply");
    expect(within(bubble).getByTestId("simulated-badge")).toBeVisible();
    expect(within(bubble).getByText("Would wait for your approval")).toBeVisible();
    expect(within(bubble).getByText("Your settings ask you to approve replies before they are sent.")).toBeVisible();
    const facts = within(screen.getByTestId("facts-used"));
    expect(facts.getByText("6.000 ₺ / month")).toBeVisible();
    expect(facts.getByText(/from: Monthly membership, verified Oct 12/)).toBeVisible();
    expect(screen.queryByTestId("suggestions")).not.toBeInTheDocument();

    // Polling stops once nothing is pending.
    const settled = reads;
    await new Promise((resolve) => setTimeout(resolve, 1900));
    expect(reads).toBe(settled);
  }, 15000);

  it("explains in plain words why a person would be asked, with the suggestion marked as not sent", async () => {
    const complaint = turn({
      customer_text: "I want to complain about my last visit",
      draft: draft({
        text: null,
        suggestion_text: "We are sorry. The refund is ⟦500 ₺⟧.",
        decision: "human_required",
        reasons: ["INTENT_COMPLAINT", "SOMETHING_NEW_FROM_THE_SERVER"],
        facts_used: [],
      }),
    });
    setup("owner", { [`GET ${chatPath}`]: () => json(chat([complaint])) });
    await open();
    const bubble = await screen.findByTestId("assistant-reply");
    expect(within(bubble).getByText("A person would be asked to answer")).toBeVisible();
    expect(within(bubble).getByText("The assistant would not send a reply to this message by itself.")).toBeVisible();
    expect(within(bubble).getByText("This sounds like a complaint. Complaints are always answered by a person.")).toBeVisible();
    // an unknown reason code falls back to a generic sentence, never a raw code
    expect(within(bubble).getByText("The assistant’s rules asked for a person to check this.")).toBeVisible();
    expect(within(bubble).queryByText(/SOMETHING_NEW_FROM_THE_SERVER/)).not.toBeInTheDocument();
    const suggestion = within(bubble).getByTestId("suggestion");
    expect(within(suggestion).getByText("Wording to start from (not sent)")).toBeVisible();
    expect(within(suggestion).getByText("500 ₺").tagName).toBe("MARK");
    expect(within(bubble).queryByTestId("reply-text")).not.toBeInTheDocument();
    expect(within(bubble).queryByTestId("facts-used")).not.toBeInTheDocument();
  });

  it("shows a friendly message on a rate limit and keeps what the owner typed", async () => {
    setup("owner", {
      [`GET ${chatPath}`]: () => json(chat([turn()])),
      [`POST ${chatPath}/messages`]: () => problem(429, "TEST_CHAT_RATE_LIMITED", { params: { retry_after: 600 } }),
    });
    await open();
    await userEvent.type(await screen.findByLabelText("Customer message"), "Another question");
    await userEvent.click(screen.getByRole("button", { name: "Send test message" }));
    expect(await screen.findByText("Slow down a little")).toBeVisible();
    expect(screen.getByText("Try again in about 10 min.")).toBeVisible();
    expect(screen.getByLabelText("Customer message")).toHaveValue("Another question");
  });

  it("mentions the remaining quota only when it is low, and stops sending at zero", async () => {
    setup("owner", { [`GET ${chatPath}`]: () => json(chat([], { remaining_this_hour: 3, remaining_today: 40 })) });
    await open();
    expect(await screen.findByTestId("quota")).toHaveTextContent("3 test messages left this hour");
  });

  it("disables sending when no test messages are left", async () => {
    setup("owner", { [`GET ${chatPath}`]: () => json(chat([turn()], { remaining_this_hour: 0, remaining_today: 40 })) });
    await open();
    expect(await screen.findByTestId("quota")).toHaveTextContent("You have used the test messages for now");
    await userEvent.type(screen.getByLabelText("Customer message"), "Hello");
    expect(screen.getByRole("button", { name: "Send test message" })).toBeDisabled();
  });

  it("resets the chat and brings the starter questions back", async () => {
    let cleared = false;
    const requests = setup("owner", {
      [`GET ${chatPath}`]: () => json(chat(cleared ? [] : [turn()])),
      [`POST ${chatPath}/reset`]: () => {
        cleared = true;
        return json({ cleared: 1 });
      },
    });
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "Start over" }));
    expect(await screen.findByTestId("suggestions")).toBeVisible();
    expect(screen.queryByTestId("assistant-reply")).not.toBeInTheDocument();
    expect(requests.some((r) => r.method === "POST" && r.path === `${chatPath}/reset`)).toBe(true);
  });

  it("shows a retryable error when the chat cannot be loaded", async () => {
    let fail = true;
    setup("owner", { [`GET ${chatPath}`]: () => (fail ? problem(500, "INTERNAL_ERROR") : json(chat())) });
    await open();
    expect(await screen.findByRole("alert", undefined, { timeout: 5000 })).toBeVisible();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("suggestions")).toBeVisible();
  }, 15000);

  it("is for owners and managers only", async () => {
    const requests = setup("staff");
    await open();
    expect(screen.getByText("Only owners and managers can try the assistant.")).toBeVisible();
    expect(requests.some((r) => r.path === chatPath)).toBe(false);
  });
});

describe("FactsUsed", () => {
  it("lists each value with its source and verification date, in the workspace time zone", async () => {
    pinToday();
    await i18n.changeLanguage("en");
    render(
      <FactsUsed
        timeZone="Europe/Istanbul"
        facts={[
          { label: "Monthly membership", display: "6.000 ₺ / month", verified_at: "2026-10-12T21:30:00Z" },
          { label: "Opening hours", display: "09:00-21:00", verified_at: null },
        ]}
      />,
    );
    const items = screen.getAllByTestId("fact-used");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("6.000 ₺ / month");
    expect(items[0]).toHaveTextContent("from: Monthly membership, verified Oct 13"); // 00:30 local time on the 13th
    expect(items[1]).toHaveTextContent("from: Opening hours, verification date unknown");
  });

  it("renders nothing for an empty list unless it is told what to say", () => {
    const { container, rerender } = render(<FactsUsed facts={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<FactsUsed facts={[]} emptyLabel="No saved business facts were used." />);
    expect(screen.getByTestId("facts-used-empty")).toHaveTextContent("No saved business facts were used.");
  });

  it("displays controller mode badge and decision badge correctly", async () => {
    setup("owner", {
      [`GET ${chatPath}`]: () =>
        json(
          chat(
            [
              turn({
                controller_mode: "agent",
                draft: draft({ decision: "auto", reasons: ["basic_verified_topic"] }),
              }),
            ],
            { controller_mode: "agent" },
          ),
        ),
    });
    await open();

    // Check header/intro controller badge
    const badges = await screen.findAllByTestId("controller-badge");
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(badges[0]).toHaveTextContent("Account Agent");

    // Check decision badge
    const decisionBadge = screen.getByTestId("decision-badge");
    expect(decisionBadge).toHaveTextContent("Auto-Send");
    expect(screen.getByTestId("decision")).toHaveTextContent("This is a basic verified question and your settings allow sending automatically.");
  });

  it("displays Turkish controller badge and decision badge correctly", async () => {
    setup(
      "owner",
      {
        [`GET ${chatPath}`]: () =>
          json(
            chat(
              [
                turn({
                  controller_mode: "legacy",
                  draft: draft({ decision: "approval_required", reasons: ["booking_enquiry_requires_approval"] }),
                }),
              ],
              { controller_mode: "legacy" },
            ),
          ),
      },
      FACTS,
      "tr",
    );
    await i18n.changeLanguage("tr");
    renderApp(`/w/${WS_GOLKENT}/more/agent/test`);
    await screen.findByRole("heading", { name: "Asistanınızı deneyin", level: 1 });

    const badges = await screen.findAllByTestId("controller-badge");
    expect(badges[0]).toHaveTextContent("Standart Asistan");

    const decisionBadge = screen.getByTestId("decision-badge");
    expect(decisionBadge).toHaveTextContent("Onay Bekliyor");
    expect(screen.getByTestId("decision")).toHaveTextContent("Randevu ve rezervasyon talepleri her zaman onayınızı gerektirir.");
  });
});

describe("starter questions", () => {
  const t = (key: string, options?: Record<string, unknown>) => i18n.getFixedT("tr")(key, options);
  it("fall back to generic questions for a workspace with no facts yet", () => {
    const questions = buildSuggestions({ category: "fitness", locale: "tr", facts: [], t });
    expect(questions.length).toBeGreaterThanOrEqual(4);
    expect(questions).toContain("Saat kaçta açıksınız?");
    expect(questions).toContain("Fiyatlarınız nedir?");
    expect(questions).toContain("Üye olmadan önce deneme dersine katılabilir miyim?");
  });
  it("name only usable facts, in the business language, and never exceed six", () => {
    const facts = [...FACTS, fact({ id: "f5", key: "service.pilates", category: "service", label: { tr: "Pilates", en: "Pilates" } }), fact({ id: "f6", key: "booking.how", category: "booking" }), fact({ id: "f7", key: "contact.phone", category: "contact" })];
    const questions = buildSuggestions({ category: "beauty_wellness", locale: "tr", facts, t });
    expect(questions.length).toBeLessThanOrEqual(6);
    expect(questions).toContain("Aylık üyelik ne kadar?");
    expect(questions.join(" ")).not.toContain("Taslak paket");
    expect(new Set(questions).size).toBe(questions.length);
  });
});

describe("assistant page entry", () => {
  const waitForTitle = () => waitFor(() => expect(screen.getByRole("heading", { name: "Account assistant" })).toBeVisible());
  it.each([
    ["owner", true],
    ["manager", true],
    ["staff", false],
  ])("offers the test chat to %s: %s", async (role, offered) => {
    setup(role, { [`GET ${base}/social-accounts`]: () => json({ items: [], next_cursor: null }) });
    await i18n.changeLanguage("en");
    renderApp(`/w/${WS_GOLKENT}/more/agent`);
    await waitForTitle();
    const link = screen.queryByRole("link", { name: "Try your assistant" });
    if (offered) expect(link).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/agent/test`);
    else expect(link).toBeNull();
  });
});
