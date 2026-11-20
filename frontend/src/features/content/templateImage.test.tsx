import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ContentItem, Me, TemplateImageState } from "@/api/types";
import { CONTENT_ID, MEDIA_ID, contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const LIST_URL = `${BASE}/content-items`;
const ITEM_URL = `${LIST_URL}/${CONTENT_ID}`;
const ITEM_PAGE = `/w/${WS_GOLKENT}/content/${CONTENT_ID}`;
const NEW_MEDIA = "e5000000-0000-4000-8000-0000000000aa";
const NEW_ITEM = "c5000000-0000-4000-8000-0000000000bb";

const originalCreate = URL.createObjectURL;
const originalRevoke = URL.revokeObjectURL;
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
});

const jpeg = () => new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), { headers: { "content-type": "image/jpeg" } });

type Handlers = Record<string, (request: RecordedRequest) => Response>;

function meWith(role: "owner" | "manager" | "staff"): Me {
  return { ...ME, memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)) };
}

const FACTS = [
  fact(),
  fact({ id: "f0000000-0000-4000-8000-000000000002", key: "pricing.day_pass", label: { tr: "Günlük giriş", en: "Day pass" }, display: "300 ₺" }),
  fact({ id: "f0000000-0000-4000-8000-000000000003", key: "pricing.draft", label: { tr: "Taslak fiyat", en: "Draft price" }, usable: false, state: "unverified", status: "unverified" }),
  fact({ id: "f0000000-0000-4000-8000-000000000004", key: "contact.phone", category: "contact", value_type: "phone", label: { tr: "Telefon", en: "Phone" }, display: "0212" }),
];

function routes(extra: Handlers = {}, role: "owner" | "manager" | "staff" = "owner"): Handlers {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "Pivoris", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(meWith(role)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: FACTS }),
    [`GET ${BASE}/social-accounts`]: () => json({ items: [socialAccount()], next_cursor: null }),
    [`GET ${LIST_URL}`]: () => json({ items: [], next_cursor: null }),
    [`POST ${BASE}/content/template-images/preview`]: jpeg,
    [`GET ${BASE}/media/${MEDIA_ID}/content`]: jpeg,
    [`GET ${BASE}/media/${NEW_MEDIA}/content`]: jpeg,
    ...extra,
  };
}

const asset = () => ({
  id: NEW_MEDIA,
  status: "ready",
  width: 1080,
  height: 1350,
  mime_type: "image/jpeg",
  byte_size: 1000,
  original_filename: "template-price_card-feed.png",
  rejection_code: null,
  created_at: "2026-10-20T10:00:00Z",
  render_record: {},
});

const posts = (requests: RecordedRequest[], path: string) => requests.filter((r) => r.method === "POST" && r.path === path);

const state = (overrides: Partial<TemplateImageState> = {}): TemplateImageState => ({
  template: "price_card",
  format: "feed",
  language: "tr",
  rendered_at: "2026-10-20T10:00:00Z",
  facts: [{ key: "pricing.membership_monthly", label: { tr: "Aylık üyelik", en: "Monthly membership" }, recorded_version: 1, current_version: 2, usable: true }],
  stale: true,
  can_rerender: true,
  ...overrides,
});

const templateItem = (overrides: Partial<ContentItem> = {}) =>
  contentItem({ media_asset_id: MEDIA_ID, template_image: state(), ...overrides });

describe("template picker in the editor", () => {
  it("lists only verified prices, previews by fact key and attaches the stored image to the draft", async () => {
    const item = contentItem({ content_type: "feed_image" });
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(item),
        [`POST ${BASE}/content/template-images`]: () => json(asset(), 201),
        [`PATCH ${ITEM_URL}`]: () => json({ ...item, version: 2, media_asset_id: NEW_MEDIA }),
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Şablondan görsel oluştur" }));
    const dialog = await screen.findByRole("dialog", { name: "Şablondan görsel" });

    const select = within(dialog).getByLabelText("Fiyat");
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Bir fiyat seçin", "Aylık üyelik · 6.000 ₺ / ay", "Günlük giriş · 300 ₺"]);
    expect(within(dialog).getByText("Önizlemeyi görmek için alanları doldurun.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Bu görseli kullan" })).toBeDisabled();

    await user.selectOptions(select, "pricing.membership_monthly");
    await waitFor(() => expect(posts(requests, `${BASE}/content/template-images/preview`)).toHaveLength(1));
    // The body names the fact by key and the format of the open item; no value is ever sent.
    expect(posts(requests, `${BASE}/content/template-images/preview`)[0]!.body).toEqual({
      template: "price_card",
      format: "feed",
      fact_key: "pricing.membership_monthly",
    });
    expect(await within(dialog).findByAltText("Şablon görselinin önizlemesi")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Bu görseli kullan" }));
    await waitFor(() => expect(requests.some((r) => r.method === "PATCH" && r.path === ITEM_URL)).toBe(true));
    expect(posts(requests, `${BASE}/content/template-images`)[0]!.body).toMatchObject({ template: "price_card", fact_key: "pricing.membership_monthly" });
    const patch = requests.find((r) => r.method === "PATCH" && r.path === ITEM_URL)!;
    expect(patch.body).toEqual({ media_asset_id: NEW_MEDIA, expected_version: 1 });
    // Saving the image never schedules or submits anything.
    expect(requests.some((r) => r.path.endsWith("/submit"))).toBe(false);
  });

  it("needs a headline and a text for an announcement and shows a refusal for typed values", async () => {
    const item = contentItem({ content_type: "story_image" });
    let refuse = false;
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(item),
        [`POST ${BASE}/content/template-images/preview`]: () => (refuse ? problem(422, "TEMPLATE_TEXT_UNGROUNDED", { params: { fields: ["body"] } }) : jpeg()),
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Şablondan görsel oluştur" }));
    const dialog = await screen.findByRole("dialog", { name: "Şablondan görsel" });
    await user.click(within(dialog).getByLabelText("Duyuru"));
    expect(within(dialog).getByLabelText("Story (9:16)")).toBeChecked(); // from the open story
    await user.type(within(dialog).getByLabelText("Başlık"), "Yeni sınıf");
    expect(posts(requests, `${BASE}/content/template-images/preview`)).toHaveLength(0); // the text is still empty
    refuse = true;
    await user.type(within(dialog).getByLabelText("Metin"), "Üyelik 500 TL");
    expect(await within(dialog).findByText("Metinde doğrulanmış bir bilgi olmayan fiyat, saat, telefon veya bağlantı var.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Bu görseli kullan" })).toBeDisabled();
    const last = posts(requests, `${BASE}/content/template-images/preview`).at(-1)!;
    expect(last.body).toMatchObject({ template: "announcement", format: "story", headline: "Yeni sınıf", body: "Üyelik 500 TL" });
  });

  it("asks to verify the opening hours first when they are not usable", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem()) }));
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Şablondan görsel oluştur" }));
    const dialog = await screen.findByRole("dialog", { name: "Şablondan görsel" });
    await user.click(within(dialog).getByLabelText("Çalışma saatleri"));
    expect(await within(dialog).findByText("Çalışma saatleriniz henüz doğrulanmadı. Önce onları doğrulayın.")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "İşletme bilgilerini aç" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/more/knowledge`);
  });
});

describe("create from a template", () => {
  it("makes a new draft with the stored image from the content page and opens it", async () => {
    const created = contentItem({ id: NEW_ITEM, content_type: "story_image", media_asset_id: NEW_MEDIA, title: "Fiyat kartı: Günlük giriş" });
    const requests = mockApi(
      routes({
        [`POST ${BASE}/content/template-images`]: () => json(asset(), 201),
        [`POST ${LIST_URL}`]: () => json(created, 201),
        [`GET ${LIST_URL}/${NEW_ITEM}`]: () => json(created),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();

    await user.click(await screen.findByLabelText("Story"));
    await user.click(await screen.findByRole("button", { name: "Şablondan yeni" }));
    const dialog = await screen.findByRole("dialog", { name: "Şablondan görsel" });
    expect(within(dialog).getByLabelText("Story (9:16)")).toBeChecked();
    await user.selectOptions(within(dialog).getByLabelText("Fiyat"), "pricing.day_pass");
    await user.click(within(dialog).getByRole("button", { name: "Bu görseli kullan" }));

    expect(await within(dialog).findByText("Taslak olarak kaydedildi. Hiçbir şey yayınlanmadı.")).toBeInTheDocument();
    const body = posts(requests, LIST_URL)[0]!.body as Record<string, unknown>;
    expect(body).toMatchObject({ content_type: "story_image", title: "Fiyat kartı: Günlük giriş", media_asset_id: NEW_MEDIA });
    expect(typeof body.client_request_id).toBe("string");
    expect(requests.some((r) => r.path.endsWith("/submit") || r.path.endsWith("/reapprove"))).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Taslağı aç" }));
    expect(await screen.findByText("Fiyat kartı: Günlük giriş")).toBeInTheDocument();
  });

  it("offers the template on the Today story prompt with the story format preselected", async () => {
    mockApi(routes({ [`GET ${BASE}/home/attention`]: () => json({ drafts: 0, unanswered_comments: 0 }) }));
    renderApp(`/w/${WS_GOLKENT}`);
    const user = userEvent.setup();
    const prompt = await screen.findByTestId("week-story-prompt");
    await user.click(within(prompt).getByRole("button", { name: "Şablondan story" }));
    const dialog = await screen.findByRole("dialog", { name: "Şablondan görsel" });
    expect(within(dialog).getByLabelText("Story (9:16)")).toBeChecked();
  });
});

describe("an out-of-date template image", () => {
  it("warns, re-renders with the item version and says it needs approval again", async () => {
    let item = templateItem({ status: "scheduled" });
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(item),
        [`POST ${ITEM_URL}/template-image/rerender`]: () => {
          item = contentItem({ version: 3, status: "draft", media_asset_id: NEW_MEDIA, template_image: state({ stale: false, facts: [{ key: "pricing.membership_monthly", label: { tr: "Aylık üyelik", en: "Monthly membership" }, recorded_version: 2, current_version: 2, usable: true }] }) });
          return json(item);
        },
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();

    const notice = await screen.findByTestId("template-stale");
    expect(notice).toHaveTextContent("Bu görsel eski bir değeri gösteriyor");
    expect(notice).toHaveTextContent("Aylık üyelik");
    expect(screen.getByTestId("template-badge")).toHaveTextContent("Şablondan yapıldı: Fiyat kartı");
    await user.click(within(notice).getByRole("button", { name: "Yeni değerle yeniden oluştur" }));

    expect(await screen.findByTestId("template-rerendered")).toHaveTextContent("yeniden onay gerekir");
    const call = requests.find((r) => r.path === `${ITEM_URL}/template-image/rerender`)!;
    expect(call.body).toEqual({ expected_version: 1 });
    await waitFor(() => expect(screen.queryByTestId("template-stale")).toBeNull());
    // Nothing was approved or scheduled by the click.
    expect(requests.some((r) => r.path.endsWith("/submit") || r.path.endsWith("/reapprove"))).toBe(false);
  });

  it("hides the re-render button when the viewer cannot edit", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(templateItem({ template_image: state({ can_rerender: false }) })) }, "staff"));
    renderApp(ITEM_PAGE);
    const notice = await screen.findByTestId("template-stale");
    expect(within(notice).queryByRole("button", { name: "Yeni değerle yeniden oluştur" })).toBeNull();
  });

  it("does not offer to re-approve a held item whose image is stale", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(templateItem({ status: "on_hold", hold_reason: "FACT_CHANGED" })) }));
    renderApp(ITEM_PAGE);
    const hold = await screen.findByTestId("on-hold");
    expect(within(hold).queryByRole("button", { name: "Olduğu gibi yeniden onayla" })).toBeNull();
    expect(await screen.findByText("Önce görseli yeniden oluşturun; ardından içerik yeniden onay ister.")).toBeInTheDocument();
  });

  it("shows only the badge when the image is current", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(templateItem({ template_image: state({ stale: false }) })) }));
    renderApp(ITEM_PAGE);
    expect(await screen.findByTestId("template-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("template-stale")).toBeNull();
  });
});
