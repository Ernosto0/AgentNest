import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HASH, BASE, approval } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

function routes(items: ReturnType<typeof approval>[], extra: Record<string, () => Response> = {}) {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/approvals`]: () => json({ items, next_cursor: null }),
    ...extra,
  };
}

describe("approvals screen", () => {
  it("shows where each value of a reply comes from in the approval, from the server's mapping (D-01)", async () => {
    const DRAFT = "d1000000-0000-4000-8000-000000000009";
    const pending = approval({
      id: "a0000000-0000-4000-8000-000000000009",
      action: "reply.send",
      kind: "authorization",
      summary: {},
      subject: { type: "reply_draft", id: DRAFT, version: 1, status: "pending_approval", link: { target: "reply_draft", id: DRAFT } },
    });
    mockApi(
      routes([pending], {
        [`GET ${BASE}/reply-drafts/${DRAFT}`]: () =>
          json({
            id: DRAFT,
            conversation_id: "c1000000-0000-4000-8000-000000000001",
            status: "pending_approval",
            source: "ai",
            language: "tr",
            intent: "pricing",
            flags: [],
            text: "Üyelik 6.000 ₺ / ay.",
            suggestion_text: null,
            rendered_facts: [],
            facts_used: [
              { key: "pricing.membership_monthly", label: "Aylık üyelik", display: "6.000 ₺ / ay", verified_at: "2026-11-03T09:00:00Z" },
            ],
            validation: { passed: true, issues: [] },
            decision: "approval_required",
            decision_reasons: [],
            approval_id: pending.id,
            approval_state: null,
            version: 1,
            failure_code: null,
            window_ends_at: null,
            created_at: "2026-11-03T10:00:00Z",
            is_simulated: false,
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Yanıt gönderme/ }));
    const body = await screen.findByTestId("reply-approval-body");
    const row = await within(body).findByTestId("fact-used");
    expect(row).toHaveTextContent("6.000 ₺ / ay");
    expect(row).toHaveTextContent("kaynak: Aylık üyelik, doğrulama tarihi 3 Kas");
  });

  it("shows the voice transcript a reply was written from, labelled as automatic (F-03)", async () => {
    const DRAFT = "d1000000-0000-4000-8000-00000000000a";
    const pending = approval({
      id: "a0000000-0000-4000-8000-00000000000a",
      action: "reply.send",
      kind: "authorization",
      summary: {},
      subject: { type: "reply_draft", id: DRAFT, version: 1, status: "pending_approval", link: { target: "reply_draft", id: DRAFT } },
    });
    mockApi(
      routes([pending], {
        [`GET ${BASE}/reply-drafts/${DRAFT}`]: () =>
          json({
            id: DRAFT,
            conversation_id: "c1000000-0000-4000-8000-000000000001",
            status: "pending_approval",
            source: "ai",
            language: "tr",
            intent: "pricing",
            flags: [],
            text: "Üyelik 6.000 ₺ / ay.",
            suggestion_text: null,
            rendered_facts: [],
            facts_used: [],
            validation: { passed: true, issues: [] },
            decision: "approval_required",
            decision_reasons: ["TRANSCRIPT_REQUIRES_APPROVAL"],
            approval_id: pending.id,
            approval_state: null,
            version: 1,
            failure_code: null,
            window_ends_at: null,
            created_at: "2026-11-03T10:00:00Z",
            is_simulated: false,
            transcripts: [{ message_id: "m1000000-0000-4000-8000-0000000000aa", text: "Aylık üyelik ücreti ne kadar?", language: "tr" }],
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Yanıt gönderme/ }));
    const body = await screen.findByTestId("reply-approval-body");
    const transcripts = await within(body).findByTestId("draft-transcripts");
    expect(transcripts).toHaveTextContent("Yazıya çeviri (otomatik)");
    expect(transcripts).toHaveTextContent("Türkçe");
    expect(transcripts).toHaveTextContent("Aylık üyelik ücreti ne kadar?");
    expect(within(body).getByText("Sesli mesajdan yazıldı, bu yüzden her zaman sizin onayınız gerekir")).toBeInTheDocument();
  });

  it("lists what is pending and teaches when there is nothing", async () => {
    mockApi(routes([]));
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    expect(await screen.findByText("Bekleyen onay yok")).toBeInTheDocument();
    expect(screen.getByText(/onayınız gereken değişiklikler burada görünür/)).toBeInTheDocument();
  });

  it("renders any approval generically by its action, then decides with the displayed hash", async () => {
    const pending = approval({
      summary: {
        label: "Aylık üyelik",
        old_formatted: "6.000 ₺ / ay",
        new_formatted: "7.000 ₺ / ay",
        impact: { total: 2, items: [{ referrer_type: "reply_draft", counts: { pending_approval: 2 }, total: 2 }] },
      },
    });
    const requests = mockApi(
      routes([pending], {
        [`POST ${BASE}/approvals/${pending.id}/decision`]: () => json(approval({ status: "approved" })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Bilgi güncelleme/ }));
    const detail = await screen.findByTestId("approval-detail");
    expect(within(detail).getByTestId("change-from")).toHaveTextContent("6.000 ₺ / ay");
    expect(within(detail).getByTestId("change-to")).toHaveTextContent("7.000 ₺ / ay");
    expect(detail).toHaveTextContent("Yanıt taslağı: 2 adet");
    expect(detail).toHaveTextContent("Komut onayı");
    expect(detail).toHaveAttribute("data-payload-hash", HASH);

    await user.click(screen.getByRole("button", { name: "Onayla" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(true));
    const decision = requests.find((r) => r.path.endsWith("/decision"))!;
    expect(decision.body).toEqual({ decision: "approve", payload_hash: HASH, note: null });
  });

  it("rejecting sends an explicit reject", async () => {
    const pending = approval();
    const requests = mockApi(
      routes([pending], {
        [`POST ${BASE}/approvals/${pending.id}/decision`]: () => json(approval({ status: "rejected" })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bilgi güncelleme/ }));
    await user.click(await screen.findByRole("button", { name: "Reddet" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(true));
    expect(requests.find((r) => r.path.endsWith("/decision"))!.body).toMatchObject({ decision: "reject" });
  });

  it("offers no decision to someone who cannot decide", async () => {
    mockApi(routes([approval({ kind: "authorization", can_decide: false })]));
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Bilgi güncelleme/ }));
    const detail = await screen.findByTestId("approval-detail");
    expect(detail).toBeInTheDocument();
    expect(screen.getByText("Bu onay için karar verme yetkiniz yok.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Onayla" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reddet" })).toBeNull();
  });

  it("shows an expired or changed approval's error, not a success", async () => {
    const pending = approval();
    mockApi(
      routes([pending], {
        [`POST ${BASE}/approvals/${pending.id}/decision`]: () => problem(409, "APPROVAL_EXPIRED"),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bilgi güncelleme/ }));
    await user.click(await screen.findByRole("button", { name: "Onayla" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu onayın süresi doldu.");
  });

  it("keeps decided approvals in the history tab", async () => {
    mockApi(routes([approval(), approval({ id: "a0000000-0000-4000-8000-000000000002", status: "approved", can_decide: false, decided_at: "2026-10-15T12:10:00Z" })]));
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    const user = userEvent.setup();
    expect(await screen.findAllByRole("button", { name: /Bilgi güncelleme/ })).toHaveLength(1);
    await user.click(screen.getByRole("tab", { name: "Geçmiş" }));
    const rows = await screen.findAllByRole("button", { name: /Bilgi güncelleme/ });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("Onaylandı");
  });
});
