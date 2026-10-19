import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Command, Me } from "@/api/types";
import { HASH, BASE, approval, command } from "@/test/aiFixtures";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const CMD = "c0000000-0000-4000-8000-000000000001";

function me(role: "owner" | "staff"): Me {
  return {
    ...ME,
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
  };
}

function routes(extra: Record<string, () => Response> = {}, llmMode = "fake", role: "owner" | "staff" = "owner") {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: llmMode, supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me(role)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

/** GET command: the n-th call returns the n-th state (the last one repeats). */
function states(...sequence: Command[]): () => Response {
  let call = 0;
  return () => json(sequence[Math.min(call++, sequence.length - 1)]);
}

async function submit(text: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Komut"), text);
  await user.click(screen.getByRole("button", { name: "Gönder" }));
  return user;
}

const confirming = command({
  status: "awaiting_confirmation",
  command_type: "knowledge.update_fact",
  approval: approval(),
});
const cancelled = { ...confirming, status: "cancelled" as const, approval: approval({ status: "cancelled" }) };

describe("command bar", () => {
  it("sends the command, shows the confirmation, and confirms with the displayed hash", async () => {
    const requests = mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(command(), 202),
        [`GET ${BASE}/commands/${CMD}`]: states(command(), confirming, {
          ...confirming,
          status: "completed",
          approval: approval({ status: "approved", can_decide: false }),
          result: {
            message_key: "command.fact_updated",
            params: {
              label: "Aylık üyelik",
              old_display: "6.000 ₺ / ay",
              new_display: "7.000 ₺ / ay",
              version: 2,
            },
            links: [{ target: "knowledge", category: "pricing", key: "pricing.membership_monthly" }],
          },
        }),
        [`POST ${BASE}/approvals/${approval().id}/decision`]: () =>
          json(approval({ status: "approved", can_decide: false })),
        [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("Aylık üyelik artık 7.000 TL");

    // The request carries the text, an idempotency id and the CSRF token.
    const posted = requests.find((r) => r.method === "POST" && r.path === `${BASE}/commands`)!;
    expect(posted.body).toMatchObject({ text: "Aylık üyelik artık 7.000 TL" });
    expect((posted.body as { client_request_id: string }).client_request_id).toMatch(/\S{8,}/);
    expect(posted.headers.get("X-CSRF-Token")).toBe("csrf-token-for-tests");

    expect(await screen.findByText("Anlıyorum…")).toBeInTheDocument();
    const card = await screen.findByTestId("confirmation-card", undefined, { timeout: 4000 });
    expect(within(card).getByTestId("change-from")).toHaveTextContent("6.000 ₺ / ay");
    expect(within(card).getByTestId("change-to")).toHaveTextContent("7.000 ₺ / ay");
    expect(card).toHaveTextContent("Bu değişiklik başka bir taslağı veya içeriği etkilemiyor.");
    expect(card).toHaveAttribute("data-payload-hash", HASH);

    await userEvent.setup().click(within(card).getByRole("button", { name: "Onayla" }));

    const decision = await waitFor(() => {
      const found = requests.find((r) => r.path === `${BASE}/approvals/${approval().id}/decision`);
      expect(found).toBeDefined();
      return found!;
    });
    expect(decision.body).toEqual({ decision: "approve", payload_hash: HASH, note: null });

    const result = await screen.findByTestId("command-result", undefined, { timeout: 4000 });
    expect(result).toHaveTextContent("Aylık üyelik güncellendi: 6.000 ₺ / ay → 7.000 ₺ / ay (sürüm 2).");
    expect(within(result).getByRole("link", { name: "İşletme bilgilerini aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/knowledge/pricing`,
    );
  }, 15_000);

  it("withdrawing cancels the command and never approves", async () => {
    const requests = mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(confirming, 202),
        // The first read shows the confirmation; after the cancel the server answers "cancelled".
        [`GET ${BASE}/commands/${CMD}`]: states(confirming, cancelled),
        [`POST ${BASE}/commands/${CMD}/cancel`]: () => json(cancelled),
        [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = await submit("Aylık üyelik artık 7.000 TL");

    await user.click(await screen.findByRole("button", { name: "Vazgeç" }));
    expect(await screen.findByText("İptal edildi. Hiçbir şey değişmedi.")).toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(false);
  });

  it("asks which fact was meant and continues with the chosen option", async () => {
    const asking = command({
      status: "needs_clarification",
      clarification: {
        question_key: "command.clarify.which_fact",
        params: { raw: "7000" },
        options: [
          { id: "pricing.membership_monthly", label: "Aylık üyelik · 6.000 ₺ / ay" },
          { id: "pricing.membership_3_months", label: "3 aylık üyelik · 16.500 ₺ / paket" },
          { id: "pricing.reformer_8_sessions", label: "Reformer 8 seans · 4.800 ₺ / paket" },
        ],
      },
    });
    const requests = mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(asking, 202),
        [`GET ${BASE}/commands/${CMD}`]: states(asking),
        [`POST ${BASE}/commands/${CMD}/clarification`]: () => json(confirming, 202),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = await submit("fiyat artık 7000");

    const chips = await screen.findByTestId("clarification");
    expect(chips).toHaveTextContent("“7000” hangi bilgi için?");
    expect(within(chips).getAllByRole("button")).toHaveLength(4); // three options and "Vazgeç"
    await user.click(within(chips).getByRole("button", { name: /3 aylık üyelik/ }));

    expect(await screen.findByTestId("confirmation-card")).toBeInTheDocument();
    const answer = requests.find((r) => r.path.endsWith("/clarification"))!;
    expect(answer.body).toEqual({ option_id: "pricing.membership_3_months" });
  });

  it("asks which amount was meant when the notation is ambiguous", async () => {
    const asking = command({
      status: "needs_clarification",
      clarification: {
        question_key: "command.clarify.which_value",
        params: { raw: "7.000", label: "Aylık üyelik" },
        options: [
          { id: "0", label: "7.000 ₺" },
          { id: "1", label: "7 ₺" },
        ],
      },
    });
    mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(asking, 202),
        [`GET ${BASE}/commands/${CMD}`]: states(asking),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("Aylık üyelik artık 7.000");
    expect(await screen.findByTestId("clarification")).toHaveTextContent(
      "“7.000” (Aylık üyelik) için hangi tutarı kastettiniz?",
    );
  });

  it("answers 'not something I can do' with a pointer to Content, and never offers a decision", async () => {
    const unsupported = command({
      status: "unsupported",
      raw_text: "gönderiyi şimdi yayınla",
      result: {
        message_key: "command.unsupported",
        params: {
          reason: "publish",
          suggestions: ["command.suggest.update_price", "command.suggest.ask_price", "command.suggest.activity"],
        },
        links: [{ target: "content" }],
      },
    });
    mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(unsupported, 202),
        [`GET ${BASE}/commands/${CMD}`]: states(unsupported),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("gönderiyi şimdi yayınla");

    const result = await screen.findByTestId("command-result");
    expect(result).toHaveTextContent("Bunu henüz yapamıyorum");
    expect(result).toHaveTextContent("Gönderi yayınlamak komutla yapılamaz.");
    expect(within(result).getByRole("link", { name: "İçeriğe git" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content`,
    );
    expect(result).toHaveTextContent("“Aylık üyelik artık 7.000 TL”");
    expect(screen.queryByRole("button", { name: "Onayla" })).toBeNull();
  });

  it("shows a plain-language failure from the error code", async () => {
    const failed = command({
      status: "failed",
      error_code: "LLM_UNAVAILABLE",
      result: { message_key: "command.failed", params: { error_code: "LLM_UNAVAILABLE" }, links: [] },
    });
    mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(failed, 202),
        [`GET ${BASE}/commands/${CMD}`]: states(failed),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("Aylık üyelik artık 7.000 TL");
    const result = await screen.findByTestId("command-result");
    expect(result).toHaveTextContent("Yapay zekâ hizmetine şu anda ulaşılamıyor.");
    expect(result).toHaveAttribute("data-error", "LLM_UNAVAILABLE");
  });

  it("explains that a staff confirmation is only a suggestion", async () => {
    mockApi(
      routes(
        {
          [`POST ${BASE}/commands`]: () => json(confirming, 202),
          [`GET ${BASE}/commands/${CMD}`]: states(confirming),
        },
        "fake",
        "staff",
      ),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("Aylık üyelik artık 7.000 TL");
    expect(await screen.findByTestId("confirmation-card")).toHaveTextContent(
      "onaylarsanız bir öneri olarak sahibe iletilir",
    );
  });

  it("reports a stale confirmation instead of pretending it worked", async () => {
    mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(confirming, 202),
        [`GET ${BASE}/commands/${CMD}`]: states(confirming),
        [`POST ${BASE}/approvals/${approval().id}/decision`]: () => problem(409, "APPROVAL_STALE"),
        [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = await submit("Aylık üyelik artık 7.000 TL");
    await user.click(await screen.findByRole("button", { name: "Onayla" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Onaylamak üzere olduğunuz bilgi değişti.");
  });

  it("keeps the text when sending fails", async () => {
    mockApi(routes({ [`POST ${BASE}/commands`]: () => problem(422, "VALIDATION_FAILED") }));
    renderApp(`/w/${WS_GOLKENT}`);
    await submit("x");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Komut")).toHaveValue("x");
  });

  it("does not send an empty command", async () => {
    const requests = mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}`);
    const send = await screen.findByRole("button", { name: "Gönder" });
    expect(send).toBeDisabled();
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });
});

describe("offline demo AI indicator", () => {
  it("is shown for the fake provider and hidden for a real one", async () => {
    mockApi(routes({}, "fake"));
    const { unmount } = renderApp(`/w/${WS_GOLKENT}`);
    expect(await screen.findByTestId("ai-mode")).toHaveTextContent("Çevrimdışı demo yapay zekâsı");
    unmount();
    vi.unstubAllGlobals();

    mockApi(routes({}, "real"));
    renderApp(`/w/${WS_GOLKENT}`);
    await screen.findByLabelText("Komut");
    await waitFor(() => expect(screen.queryByTestId("ai-mode")).toBeNull());
  });
});
