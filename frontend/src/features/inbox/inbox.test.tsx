import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Conversation, ConversationDetail, ReplyDraft } from "@/api/types";
import { approval, HASH } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const CONVERSATION_ID = "c1000000-0000-4000-8000-000000000001";
const DRAFT_ID = "d1000000-0000-4000-8000-000000000001";
const APPROVAL_ID = "a0000000-0000-4000-8000-000000000001";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: CONVERSATION_ID,
    customer_handle: "Ayşe",
    customer_number: 4821,
    last_message_preview: "Aylık üyelik ne kadar?",
    last_message_at: "2026-10-15T12:00:00Z",
    attention: "needs_approval",
    handling_mode: "automatic",
    window_ends_at: new Date(Date.now() + 20 * 3_600_000).toISOString(),
    is_simulated: true,
    ...overrides,
  };
}

function draft(overrides: Partial<ReplyDraft> = {}): ReplyDraft {
  const text = "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay.";
  const start = text.indexOf("6.000");
  return {
    id: DRAFT_ID,
    conversation_id: CONVERSATION_ID,
    status: "pending_approval",
    source: "ai",
    language: "tr",
    intent: "pricing",
    flags: [],
    text,
    suggestion_text: null,
    rendered_facts: [
      {
        fact_id: "f1000000-0000-4000-8000-000000000001",
        key: "pricing.membership_monthly",
        label: "Aylık üyelik",
        display: "6.000 ₺ / ay",
        version: 1,
        span: [start, start + "6.000 ₺ / ay".length],
      },
    ],
    validation: { passed: true, issues: [] },
    decision: "approval_required",
    decision_reasons: ["POLICY_REQUIRES_APPROVAL"],
    approval_id: APPROVAL_ID,
    approval_state: null,
    version: 1,
    failure_code: null,
    window_ends_at: null,
    created_at: "2026-10-15T12:00:00Z",
    is_simulated: true,
    ...overrides,
  };
}

function detail(open: ReplyDraft | null): ConversationDetail {
  return {
    conversation: conversation(),
    messages: [
      {
        id: "m1000000-0000-4000-8000-000000000001",
        direction: "inbound",
        sender_kind: "customer",
        text: "Aylık üyelik ne kadar?",
        attachments: [],
        provider_timestamp: "2026-10-15T12:00:00Z",
        is_simulated: true,
      },
    ],
    open_draft: open,
    recent_drafts: [],
  };
}

function routes(extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

describe("inbox", () => {
  it("lists conversations with why they need you and the simulation badge", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations`]: () =>
          json({
            items: [
              conversation(),
              conversation({ id: "c2", customer_handle: null, attention: "needs_human", last_message_preview: null }),
            ],
            next_cursor: null,
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox`);
    expect(await screen.findByText("Ayşe")).toBeInTheDocument();
    expect(screen.getByText("Müşteri #4821")).toBeInTheDocument();
    const chips = screen.getAllByTestId("attention-chip").map((el) => el.textContent);
    expect(chips).toEqual(["Onay bekliyor", "Size gerek var"]);
    expect(screen.getAllByTestId("simulated-badge").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("window-timer")[0]).toHaveTextContent(/saat kaldı/);
  });

  it("shows an empty inbox with a hint", async () => {
    mockApi(routes({ [`GET ${BASE}/conversations`]: () => json({ items: [], next_cursor: null }) }));
    renderApp(`/w/${WS_GOLKENT}/inbox`);
    expect(await screen.findByText("Burada konuşma yok")).toBeInTheDocument();
  });

  it("shows the draft with the value as a source chip and approves with the displayed hash", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () => json(detail(draft())),
        [`GET ${BASE}/approvals/${APPROVAL_ID}`]: () => json(approval({ id: APPROVAL_ID, action: "reply.send", kind: "authorization" })),
        [`POST ${BASE}/approvals/${APPROVAL_ID}/decision`]: () => json(approval({ status: "approved" })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const user = userEvent.setup();

    const card = await screen.findByTestId("draft-card");
    expect(within(card).getByTestId("draft-text")).toHaveTextContent("Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay.");
    await user.click(within(card).getByTestId("fact-chip"));
    expect(await within(card).findByText(/Kaynak: Aylık üyelik, doğrulandı/)).toBeInTheDocument();
    expect(within(card).getByText("Otomatik gönderim kapalı")).toBeInTheDocument();
    expect(within(card).getByTestId("simulated-badge")).toBeInTheDocument();

    await user.click(await within(card).findByRole("button", { name: "Onayla ve gönder" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(true));
    expect(requests.find((r) => r.path.endsWith("/decision"))!.body).toEqual({
      decision: "approve",
      payload_hash: HASH,
      note: null,
    });
  });

  it("offers no decision to someone who may not approve", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () => json(detail(draft())),
        [`GET ${BASE}/approvals/${APPROVAL_ID}`]: () => json(approval({ id: APPROVAL_ID, can_decide: false })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    expect(await screen.findByText("Bu yanıtı bir sahip ya da yönetici onaylamalı.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Onayla ve gönder" })).not.toBeInTheDocument();
  });

  it("tells staff who must approve a pending reply and by when", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(
            detail(
              draft({
                approval_state: {
                  status: "pending",
                  expires_at: "2026-10-16T09:30:00Z",
                  decided_by_name: null,
                  decided_at: null,
                  decision_note: null,
                },
              }),
            ),
          ),
        [`GET ${BASE}/approvals/${APPROVAL_ID}`]: () => json(approval({ id: APPROVAL_ID, can_decide: false })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    expect(await within(card).findByText("Bu yanıtı bir sahip ya da yönetici onaylamalı.")).toBeInTheDocument();
    const note = await within(card).findByTestId("approval-state");
    expect(note).toHaveAttribute("data-approval-status", "pending");
    expect(note).toHaveTextContent(/Son onay zamanı: .*(16|10)/);
  });

  it("does not show the pending note to someone who can approve", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(
            detail(
              draft({
                approval_state: {
                  status: "pending",
                  expires_at: "2026-10-16T09:30:00Z",
                  decided_by_name: null,
                  decided_at: null,
                  decision_note: null,
                },
              }),
            ),
          ),
        [`GET ${BASE}/approvals/${APPROVAL_ID}`]: () => json(approval({ id: APPROVAL_ID, can_decide: true })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    expect(await within(card).findByRole("button", { name: "Onayla ve gönder" })).toBeInTheDocument();
    expect(within(card).queryByTestId("approval-state")).not.toBeInTheDocument();
  });

  it.each([
    [
      "approved",
      "queued",
      { decided_by_name: "Cem Yılmaz", decided_at: "2026-10-15T13:00:00Z", decision_note: "Fiyat doğru." },
      [/Cem Yılmaz onayladı/, /Not: Fiyat doğru\./],
    ],
    [
      "rejected",
      "rejected",
      { decided_by_name: "Cem Yılmaz", decided_at: "2026-10-15T13:00:00Z", decision_note: "Önce fiyatı güncelleyin." },
      [/Cem Yılmaz reddetti/, /Not: Önce fiyatı güncelleyin\./],
    ],
    ["expired", "expired", { decided_by_name: null, decided_at: null, decision_note: null }, [/Onay süresi doldu/]],
  ] as const)("shows staff a %s reply with who decided and the note", async (status, draftStatus, decision, texts) => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(
            detail(
              draft({
                status: draftStatus,
                approval_state: { status, expires_at: "2026-10-16T09:30:00Z", ...decision },
              }),
            ),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    const note = await within(card).findByTestId("approval-state");
    expect(note).toHaveAttribute("data-approval-status", status);
    for (const text of texts) expect(note).toHaveTextContent(text);
    expect(within(card).queryByRole("button", { name: "Onayla ve gönder" })).not.toBeInTheDocument();
  });

  it("says nothing about a reply that policy approved", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(
            detail(
              draft({
                status: "sent",
                approval_state: {
                  status: "approved",
                  expires_at: "2026-10-16T09:30:00Z",
                  decided_by_name: null,
                  decided_at: "2026-10-15T12:00:00Z",
                  decision_note: null,
                },
              }),
            ),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    expect(within(card).queryByTestId("approval-state")).not.toBeInTheDocument();
  });

  it("hands a complaint to you: no sendable text, the suggestion can seed your reply", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(
            detail(
              draft({
                status: "needs_human",
                text: null,
                suggestion_text: "Özür dileriz, sizi arayacağız.",
                rendered_facts: [],
                decision_reasons: ["INTENT_COMPLAINT", "FLAG_REFUND"],
                approval_id: null,
              }),
            ),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const user = userEvent.setup();
    const card = await screen.findByTestId("draft-card");
    expect(within(card).getByText("Bu mesaja kendiniz yanıt vermelisiniz.")).toBeInTheDocument();
    expect(within(card).getByText("Şikayet")).toBeInTheDocument();
    expect(within(card).getByText("İade içeriyor")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Onayla ve gönder" })).not.toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Yanıtım olarak kullan" }));
    expect(screen.getByLabelText("Yanıtınız")).toHaveValue("Özür dileriz, sizi arayacağız.");
  });

  it("explains a stricter class borrowed from a quoted value as a reason chip", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(detail(draft({ decision_reasons: ["POLICY_REQUIRES_APPROVAL", "CONTAINS_PRICING"] }))),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    expect(within(card).getByText("Otomatik gönderim kapalı")).toBeInTheDocument();
    expect(within(card).getByText("Fiyat içeriyor, fiyat ayarı geçerli")).toBeInTheDocument();
  });

  it("shows a send that is being checked, never as sent", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () =>
          json(detail(draft({ status: "outcome_unknown", approval_id: null }))),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const card = await screen.findByTestId("draft-card");
    expect(within(card).getByRole("status")).toHaveTextContent("Gönderilip gönderilmediği kontrol ediliyor");
    expect(within(card).queryByText("Gönderildi")).not.toBeInTheDocument();
  });

  it("sends your own reply with a request id and shows the warnings", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () => json(detail(null)),
        [`POST ${BASE}/conversations/${CONVERSATION_ID}/replies`]: () =>
          json(
            {
              draft: draft({ source: "owner", status: "queued" }),
              warnings: [{ code: "MONEY", span: [0, 5], text: "5.000 ₺", matches_verified: false }],
            },
            201,
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Yanıtınız"), "Aylık üyelik 5.000 ₺");
    await user.click(screen.getByRole("button", { name: "Yanıtı gönder" }));
    expect(await screen.findByTestId("reply-warnings")).toHaveTextContent("5.000 ₺");
    const sent = requests.find((r) => r.path.endsWith("/replies"))!;
    expect(sent.body).toMatchObject({ text: "Aylık üyelik 5.000 ₺" });
    expect((sent.body as { client_request_id: string }).client_request_id).toBeTruthy();
  });

  it("takes a conversation over and hands it back", async () => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/conversations/${CONVERSATION_ID}`]: () => json(detail(null)),
        [`POST ${BASE}/conversations/${CONVERSATION_ID}/takeover`]: () =>
          json(conversation({ handling_mode: "human" })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/inbox/${CONVERSATION_ID}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Devral" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/takeover"))).toBe(true));
  });
});
