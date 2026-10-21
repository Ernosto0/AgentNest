import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Command, Me } from "@/api/types";
import { CommandResultCard } from "@/features/commands/CommandResultCard";
import { CurrentWorkspaceContext } from "@/features/workspaces/context";
import { describeNotification } from "@/features/notifications/describe";
import i18n from "@/i18n";
import { BASE, HASH, approval, command, notification } from "@/test/aiFixtures";
import { CONTENT_ID, MEDIA_ID, contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const ITEM_URL = `${BASE}/content-items/${CONTENT_ID}`;
const CMD = "c0000000-0000-4000-8000-000000000001";
const t = i18n.t.bind(i18n);

function me(role: "owner" | "staff"): Me {
  return {
    ...ME,
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
  };
}

function routes(extra: Record<string, () => Response> = {}, role: "owner" | "staff" = "owner") {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me(role)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [fact()] }),
    ...extra,
  };
}

const image = () => new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { headers: { "content-type": "image/jpeg" } });

describe("approval of a content.publish", () => {
  const SUBJECT_VERSION = 3;
  const publishApproval = (overrides = {}) =>
    approval({
      id: "a0000000-0000-4000-8000-0000000000aa",
      kind: "authorization",
      action: "content.publish",
      summary: {
        content_id: CONTENT_ID,
        content_type: "feed_image",
        title: "Yeni dönem kampanyası",
        scheduled_at: "2026-10-21T16:00:00Z",
      },
      subject: {
        type: "content_item",
        id: CONTENT_ID,
        version: SUBJECT_VERSION,
        status: "pending_approval",
        link: { target: "content", id: CONTENT_ID },
      },
      required_permission: "content.approve",
      is_simulated: true,
      ...overrides,
    });

  const open = async (extra: Record<string, () => Response>, pending = publishApproval()) => {
    const requests = mockApi(
      routes({
        [`GET ${BASE}/approvals`]: () => json({ items: [pending], next_cursor: null }),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        ...extra,
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    const user = userEvent.setup();
    const row = await screen.findByRole("button", { name: /İçerik yayınlama/ });
    // The list names the item and the time, not raw ids.
    expect(row).toHaveTextContent("Yeni dönem kampanyası");
    expect(row).toHaveTextContent("21.10.2026");
    await user.click(row);
    return { requests, user, body: await screen.findByTestId("content-approval-body") };
  };

  it("shows exactly the bound payload: caption, media and time (a feed post)", async () => {
    const { body } = await open({
      [`GET ${ITEM_URL}`]: () =>
        json(contentItem({ version: SUBJECT_VERSION, media_asset_id: MEDIA_ID, caption: "Aylık üyelik 6.000 ₺ / ay ile başlıyor." })),
    });
    expect(body).toHaveAttribute("data-stale", "false");
    expect(within(body).getByTestId("preview-caption")).toHaveTextContent("Aylık üyelik 6.000 ₺ / ay ile başlıyor.");
    expect(await within(body).findByTestId("preview-media")).toHaveAttribute("src", expect.stringMatching(/^blob:/));
    expect(within(body).getByTestId("approval-when")).toHaveTextContent("19:00 (İstanbul saati)");
    expect(body).toHaveTextContent("Gönderi · Sürüm 3");
    // No raw summary fields leak into the generic rows.
    const detail = screen.getByTestId("approval-detail");
    expect(detail).not.toHaveTextContent(CONTENT_ID);
    expect(within(detail).getByTestId("simulated-badge")).toBeInTheDocument();
  });

  it("shows the overlay text of a story and says it is not published as text", async () => {
    const { body } = await open({
      [`GET ${ITEM_URL}`]: () =>
        json(
          contentItem({
            version: SUBJECT_VERSION,
            content_type: "story_image",
            caption: null,
            media_asset_id: MEDIA_ID,
            overlay_text_suggestions: ["İlk deneme dersi ücretsiz!", "Bugün kayıt olun"],
          }),
        ),
    });
    expect(within(body).getAllByTestId("preview-overlay-item").map((li) => li.textContent)).toEqual([
      "İlk deneme dersi ücretsiz!",
      "Bugün kayıt olun",
    ]);
    expect(body).toHaveTextContent("Story ile ayrıca yayınlanmaz");
    expect(within(body).queryByTestId("preview-caption")).toBeNull();
  });

  it("approves with the displayed hash, and Reddet is a separate explicit button", async () => {
    const pending = publishApproval();
    const { requests, user } = await open(
      {
        [`GET ${ITEM_URL}`]: () => json(contentItem({ version: SUBJECT_VERSION, media_asset_id: MEDIA_ID })),
        [`POST ${BASE}/approvals/${pending.id}/decision`]: () => json({ ...pending, status: "approved", can_decide: false }),
      },
      pending,
    );
    expect(screen.getByRole("button", { name: "Reddet" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(true));
    expect(requests.find((r) => r.path.endsWith("/decision"))!.body).toEqual({
      decision: "approve",
      payload_hash: HASH,
      note: null,
    });
  });

  it("an item that changed since the request is not shown as approved text and cannot be approved", async () => {
    const { body } = await open({
      [`GET ${ITEM_URL}`]: () =>
        json(contentItem({ version: SUBJECT_VERSION + 1, media_asset_id: MEDIA_ID, caption: "Yeni, başka bir metin" })),
    });
    expect(within(body).getByTestId("approval-stale")).toHaveTextContent("sürüm 4, onaydaki sürüm 3");
    expect(within(body).queryByTestId("preview-caption")).toBeNull();
    expect(body).not.toHaveTextContent("Yeni, başka bir metin");
    expect(screen.getByRole("button", { name: "Onayla" })).toBeDisabled();
  });

  it("does not let anyone approve what could not be loaded", async () => {
    const pending = publishApproval();
    mockApi(
      routes({
        [`GET ${BASE}/approvals`]: () => json({ items: [pending], next_cursor: null }),
        [`GET ${ITEM_URL}`]: () => problem(403, "FORBIDDEN"),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.setup().click(await screen.findByRole("button", { name: /İçerik yayınlama/ }));
    expect(await screen.findByText("İçerik yüklenemedi.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Onayla" })).toBeDisabled();
  });
});

describe("notifications for content (G14)", () => {
  const note = (type: string, params: Record<string, unknown>) =>
    notification({ type, params: { content_id: CONTENT_ID, title: "Yaz kampanyası", version: 2, ...params } });
  const say = (type: string, params: Record<string, unknown> = {}) => describeNotification(t, note(type, params), "tr");

  it("describes content.on_hold by its reason", () => {
    expect(say("content.on_hold", { reason: "FACT_CHANGED" })).toBe(
      "“Yaz kampanyası” beklemeye alındı: kullandığı işletme bilgisi değişti.",
    );
    expect(say("content.on_hold", { reason: "ACCOUNT_UNAVAILABLE" })).toBe(
      "“Yaz kampanyası” beklemeye alındı: Instagram hesabı kullanılamıyor.",
    );
    expect(say("content.on_hold", { reason: null })).toBe("“Yaz kampanyası” beklemeye alındı.");
  });

  it("describes content.published and content.failed (with the cause from the catalog)", () => {
    expect(say("content.published")).toBe("“Yaz kampanyası” yayınlandı.");
    expect(say("content.failed", { reason: "MEDIA_REJECTED" })).toBe(
      "“Yaz kampanyası” yayınlanamadı: Instagram görseli işleyemedi.",
    );
    expect(say("content.failed", { reason: "A_NEW_CODE" })).toBe(
      "“Yaz kampanyası” yayınlanamadı: Yayınlanırken bir şeyler ters gitti.",
    );
  });

  it("describes them in English too", async () => {
    await i18n.changeLanguage("en");
    expect(describeNotification(t, note("content.on_hold", { reason: "FACT_CHANGED" }), "en")).toBe(
      "“Yaz kampanyası” was put on hold: business information it uses changed.",
    );
    expect(describeNotification(t, note("content.published", {}), "en")).toBe("“Yaz kampanyası” was published.");
    expect(describeNotification(t, note("content.failed", { reason: "MEDIA_REJECTED" }), "en")).toBe(
      "“Yaz kampanyası” could not be published: Instagram could not process the image.",
    );
  });

  it("the bell shows them with the simulation badge and links to the item", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/notifications`]: () =>
          json({
            items: [{ ...note("content.published", {}), is_simulated: true }],
            unread_count: 1,
            next_cursor: null,
          }),
        [`POST ${BASE}/notifications/${notification().id}/read`]: () => json(notification()),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    await userEvent.setup().click(await screen.findByRole("link", { name: /Bildirimler/ }));
    const list = await screen.findByRole("list", { name: "Bildirimler" });
    expect(within(list).getByText("“Yaz kampanyası” yayınlandı.")).toBeInTheDocument();
    expect(within(list).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${CONTENT_ID}`,
    );
  });
});

describe("command cancel_content confirmation card", () => {
  const cancelApproval = (overrides = {}) =>
    approval({
      id: "a0000000-0000-4000-8000-0000000000cc",
      action: "command.cancel_content",
      required_permission: "content.approve",
      summary: {
        label: "Salı story'si",
        content_type: "story_image",
        status: "scheduled",
        when: "21 Eki 19:00",
        content_id: CONTENT_ID,
      },
      subject: {
        type: "owner_command",
        id: CMD,
        version: 1,
        status: "awaiting_confirmation",
        link: { target: "owner_command", id: CMD },
      },
      ...overrides,
    });
  const confirming = (approvalOverrides = {}) =>
    command({
      status: "awaiting_confirmation",
      command_type: "content.cancel_scheduled",
      raw_text: "yarınki story'yi iptal et",
      approval: cancelApproval(approvalOverrides),
    });

  async function submit(text: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Komut"), text);
    await user.click(screen.getByRole("button", { name: "Gönder" }));
    return user;
  }

  it("names the item, its type, status and time, then cancels with the displayed hash", async () => {
    let decided = false;
    const completed: Command = {
      ...confirming(),
      status: "completed",
      approval: cancelApproval({ status: "approved", can_decide: false }),
      result: {
        message_key: "command.content_cancelled",
        params: { title: "Salı story'si", when: "21 Eki 19:00" },
        links: [{ target: "content", id: CONTENT_ID }],
      },
    };
    const requests = mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(confirming(), 202),
        [`GET ${BASE}/commands/${CMD}`]: () => json(decided ? completed : confirming()),
        [`POST ${BASE}/approvals/${cancelApproval().id}/decision`]: () => {
          decided = true;
          return json(cancelApproval({ status: "approved", can_decide: false }));
        },
        [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = await submit("yarınki story'yi iptal et");

    const card = await screen.findByTestId("confirmation-card", undefined, { timeout: 4000 });
    expect(card).toHaveAttribute("data-payload-hash", HASH);
    expect(within(card).getByRole("heading", { name: "Bu içerik iptal edilsin mi?" })).toBeInTheDocument();
    const summary = within(card).getByTestId("cancel-content-summary");
    expect(summary).toHaveTextContent("Salı story'si");
    expect(summary).toHaveTextContent("Story");
    // The status is the item's own: scheduled is not published (INV-18).
    expect(summary.querySelector("[data-status]")).toHaveAttribute("data-status", "scheduled");
    expect(summary).toHaveTextContent("Zamanlandı");
    expect(within(card).getByTestId("cancel-content-when")).toHaveTextContent("21 Eki 19:00");
    expect(card).toHaveTextContent("İptal ederseniz bu içerik yayınlanmaz");
    expect(within(card).getByRole("link", { name: "İçeriği aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${CONTENT_ID}`,
    );
    // It is not the fact card: no old and new value rows, no fact impact text.
    expect(within(card).queryByTestId("change-from")).toBeNull();
    expect(card).not.toHaveTextContent("Bu değişiklik başka bir taslağı veya içeriği etkilemiyor.");

    await user.click(within(card).getByRole("button", { name: "Evet, iptal et" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(true));
    expect(requests.find((r) => r.path.endsWith("/decision"))!.body).toEqual({
      decision: "approve",
      payload_hash: HASH,
      note: null,
    });

    const result = await screen.findByTestId("command-result", undefined, { timeout: 4000 });
    expect(result).toHaveTextContent("“Salı story'si” iptal edildi (21 Eki 19:00). Yayınlanmayacak.");
    expect(within(result).getByRole("link", { name: "İçeriği aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${CONTENT_ID}`,
    );
  }, 15_000);

  it("withdrawing leaves the content alone", async () => {
    const withdrawn = { ...confirming(), status: "cancelled" as const, approval: cancelApproval({ status: "cancelled" }) };
    let gone = false;
    const requests = mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(confirming(), 202),
        [`GET ${BASE}/commands/${CMD}`]: () => json(gone ? withdrawn : confirming()),
        [`POST ${BASE}/commands/${CMD}/cancel`]: () => {
          gone = true;
          return json(withdrawn);
        },
        [`GET ${BASE}/approvals`]: () => json({ items: [], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = await submit("yarınki story'yi iptal et");
    await user.click(await screen.findByRole("button", { name: "Vazgeç" }));
    expect(await screen.findByText("İptal edildi. Hiçbir şey değişmedi.")).toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith("/decision"))).toBe(false);
  });

  it("the approvals screen renders the same item summary for it", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/approvals`]: () => json({ items: [cancelApproval()], next_cursor: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/approvals`);
    await userEvent.setup().click(await screen.findByRole("button", { name: /İçerik iptali/ }));
    const detail = await screen.findByTestId("approval-detail");
    expect(within(detail).getByTestId("cancel-content-summary")).toHaveTextContent("Salı story'si");
    // The raw ids and fields of the summary are not dumped as rows.
    expect(detail).not.toHaveTextContent(CONTENT_ID);
  });
});

describe("results of the content commands", () => {
  const completed = (message_key: string, params: Record<string, unknown>, links: unknown[] = []): Command =>
    command({ status: "completed", result: { message_key, params, links: links as never } });
  const failed = (message_key: string, params: Record<string, unknown>, error_code: string): Command =>
    command({ status: "failed", error_code, result: { message_key, params, links: [{ target: "content", id: CONTENT_ID }] } });

  function show(cmd: Command) {
    return render(
      <MemoryRouter>
        <CurrentWorkspaceContext.Provider value={{ workspace: workspace(WS_GOLKENT), role: "owner" }}>
          <CommandResultCard command={cmd} />
        </CurrentWorkspaceContext.Provider>
      </MemoryRouter>,
    );
  }
  const link = [{ target: "content", id: CONTENT_ID }];

  it("content.create_draft: a draft was made, with a link to it", () => {
    show(completed("command.draft_created", { title: "Deneme dersi için story", content_type: "story_image" }, link));
    const result = screen.getByTestId("command-result");
    expect(result).toHaveTextContent("“Deneme dersi için story” taslağı oluşturuldu (Story). Metin hazırlanıyor");
    expect(within(result).getByRole("link", { name: "İçeriği aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content/${CONTENT_ID}`,
    );
  });

  it("content.cancel_scheduled: cancelled, or changed meanwhile, or not cancellable", () => {
    const { unmount } = show(completed("command.content_cancelled", { title: "Salı story'si", when: null }, link));
    expect(screen.getByTestId("command-result")).toHaveTextContent("“Salı story'si” iptal edildi. Yayınlanmayacak.");
    unmount();

    const meanwhile = show(failed("command.content_changed_meanwhile", {}, "VERSION_CONFLICT"));
    expect(screen.getByTestId("command-result")).toHaveTextContent("bu yüzden iptal edilmedi");
    expect(screen.getByTestId("command-result")).toHaveAttribute("data-error", "VERSION_CONFLICT");
    meanwhile.unmount();

    show(failed("command.content_not_cancellable", { title: "Salı story'si", status: "published" }, "CONFLICT_STATE"));
    expect(screen.getByTestId("command-result")).toHaveTextContent("“Salı story'si” iptal edilemez (durumu: Yayınlandı).");
  });

  it("query.content_status: the item's own state, never more (scheduled is not published)", () => {
    const { unmount } = show(
      completed(
        "command.content_status",
        {
          title: "Salı story'si",
          content_type: "story_image",
          status: "scheduled",
          when: "21 Eki 19:00",
          is_simulated: true,
          hold_reason: null,
          error_code: null,
        },
        link,
      ),
    );
    const result = screen.getByTestId("command-result");
    expect(result).toHaveTextContent("“Salı story'si” (Story): Zamanlandı · 21 Eki 19:00");
    expect(result).not.toHaveTextContent("Yayınlandı");
    expect(within(result).getByTestId("simulated-badge")).toBeInTheDocument();
    unmount();

    show(
      completed("command.content_status", {
        title: "Yaz postu",
        content_type: "feed_image",
        status: "on_hold",
        when: "21 Eki 19:00",
        is_simulated: false,
        hold_reason: "FACT_CHANGED",
        error_code: null,
      }),
    );
    const held = screen.getByTestId("command-result");
    expect(held).toHaveTextContent("Beklemede");
    expect(held).toHaveTextContent("Kullandığı işletme bilgisi değiştiği için beklemeye alındı.");
    expect(within(held).queryByTestId("simulated-badge")).toBeNull();
  });

  it("query.explain_failure: what and next from the catalog, retry time, and that a failure is final", () => {
    const params = {
      title: "Salı story'si",
      status: "retry_scheduled",
      error_code: "PROVIDER_UNAVAILABLE",
      what: "Instagram'a şu anda ulaşılamıyor.",
      next: "Otomatik olarak yeniden denenecek.",
      retryable: true,
      is_simulated: true,
      retry_at: "21 Eki 19:05",
    };
    const { unmount } = show(completed("command.content_failure", params, link));
    const retry = screen.getByTestId("command-result");
    expect(retry).toHaveTextContent("Instagram'a şu anda ulaşılamıyor.");
    expect(retry).toHaveTextContent("Tekrar denenecek: 21 Eki 19:05.");
    expect(within(retry).getByTestId("simulated-badge")).toBeInTheDocument();
    unmount();

    show(
      completed(
        "command.content_failure",
        { ...params, status: "failed", error_code: "MEDIA_REJECTED", what: "Instagram görseli işleyemedi.", next: "Başka bir görsel seçin.", retry_at: null, is_simulated: false },
        link,
      ),
    );
    const failure = screen.getByTestId("command-result");
    expect(failure).toHaveTextContent("Instagram görseli işleyemedi.");
    expect(failure).toHaveTextContent("Otomatik olarak tekrar denenmeyecek.");
    expect(within(failure).queryByTestId("simulated-badge")).toBeNull();
  });

  it("nothing failing, an item that is fine, an unknown reference and an unreadable draft", () => {
    const cases: [Command, string][] = [
      [completed("command.no_failure", {}, [{ target: "content" }]), "Başarısız olmuş ya da beklemeye alınmış bir içerik yok."],
      [
        completed("command.no_failure_for_item", { title: "Salı story'si", status: "scheduled" }, link),
        "“Salı story'si” sorunlu değil (durumu: Zamanlandı).",
      ],
      [failed("command.reference_not_found", { description: "yarınki post" }, "REFERENCE_NOT_FOUND"), "Söylediğiniz içeriği bulamadım."],
      [failed("command.draft_unreadable", {}, "VALIDATION_FAILED"), "Taslak için ne istediğinizi anlayamadım."],
    ];
    for (const [cmd, text] of cases) {
      const view = show(cmd);
      expect(screen.getByTestId("command-result")).toHaveTextContent(text);
      view.unmount();
    }
  });

  it("the list link (no id) goes to the content list", () => {
    show(failed("command.reference_not_found", {}, "REFERENCE_NOT_FOUND"));
    // failed() links to the item; build the list link explicitly.
    const view = show(completed("command.no_failure", {}, [{ target: "content" }]));
    const links = within(view.container).getAllByRole("link", { name: "İçeriğe git" });
    expect(links[0]).toHaveAttribute("href", `/w/${WS_GOLKENT}/content`);
  });

  it("a clarification between several content items asks which one", async () => {
    const asking = command({
      status: "needs_clarification",
      clarification: {
        question_key: "command.clarify.which_content",
        params: { count: 2 },
        options: [
          { id: "1", label: "Salı story'si · 21 Eki 19:00" },
          { id: "2", label: "Salı postu · 21 Eki 20:00" },
        ],
      },
    });
    mockApi(
      routes({
        [`POST ${BASE}/commands`]: () => json(asking, 202),
        [`GET ${BASE}/commands/${CMD}`]: () => json(asking),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}`);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Komut"), "salı günkü içeriği iptal et");
    await user.click(screen.getByRole("button", { name: "Gönder" }));
    expect(await screen.findByText("2 içerik buldum. Hangisini kastettiniz?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salı story'si · 21 Eki 19:00" })).toBeInTheDocument();
  });
});

describe("account capabilities (G4)", () => {
  it("the connection screen labels the publish capabilities", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/social-accounts`]: () => json({ items: [socialAccount()], next_cursor: null }),
        [`GET ${BASE}/automation-policies`]: () =>
          json({ auto_allowed: false, items: [], readiness_level: "ready", reviewed_at: null }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    const caps = await screen.findByTestId("account-capabilities");
    expect(caps).toHaveTextContent("Mesajlaşma, Gönderi yayınlama, Story yayınlama");
    expect(caps).not.toHaveTextContent("publish_feed_image");
  });
});
