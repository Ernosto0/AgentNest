import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ContentItem } from "@/api/types";
import { CONTENT_ID, MEDIA_ID, claimIssue, contentItem, mediaAsset } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const LIST_URL = `${BASE}/content-items`;
const ITEM_URL = `${BASE}/content-items/${CONTENT_ID}`;

type Handlers = Record<string, (request: RecordedRequest) => Response>;

function routes(extra: Handlers = {}): Handlers {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [fact()] }),
    ...extra,
  };
}

const page = (items: ContentItem[]) => json({ items, next_cursor: null });
const patches = (requests: RecordedRequest[]) => requests.filter((r) => r.method === "PATCH" && r.path === ITEM_URL);

describe("content list", () => {
  it("shows the drafts tab first, with cards that carry the status and simulation badges", async () => {
    mockApi(
      routes({
        [`GET ${LIST_URL}`]: () =>
          page([
            contentItem({ id: "d1", title: "Hafta sonu dersi", status: "draft" }),
            contentItem({
              id: "d2",
              title: "Story fikri",
              status: "pending_approval",
              content_type: "story_image",
              is_simulated: false,
            }),
          ]),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);

    expect(await screen.findByText("Hafta sonu dersi")).toBeInTheDocument();
    const cards = screen.getAllByTestId("content-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Taslak")).toBeInTheDocument();
    expect(within(cards[0]!).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Onay bekliyor")).toBeInTheDocument();
    expect(within(cards[1]!).queryByTestId("simulated-badge")).toBeNull();
    expect(cards[0]).toHaveAttribute("href", `/w/${WS_GOLKENT}/content/d1`);
  });

  it("asks the server for each tab and never lists a cancelled item", async () => {
    const byTab: Record<string, ContentItem[]> = {
      drafts: [contentItem({ id: "a", title: "Taslak A", status: "draft" })],
      scheduled: [
        contentItem({ id: "b", title: "Zamanlı B", status: "scheduled", scheduled_at: "2026-10-21T16:00:00Z" }),
        contentItem({ id: "c", title: "Yolda C", status: "publishing" }),
        contentItem({ id: "h", title: "Tekrar H", status: "retry_scheduled" }),
      ],
      published: [contentItem({ id: "d", title: "Yayında D", status: "published", published_at: "2026-10-20T10:00:00Z" })],
      problems: [
        contentItem({ id: "e", title: "Sorun E", status: "failed" }),
        contentItem({ id: "f", title: "Beklemede F", status: "on_hold" }),
        contentItem({ id: "i", title: "Reddedilen I", status: "rejected" }),
        // A misbehaving server must not make a cancelled item appear.
        contentItem({ id: "g", title: "Vazgeçilen G", status: "cancelled" }),
      ],
    };
    const requests = mockApi(
      routes({
        [`GET ${LIST_URL}`]: (request) => page(byTab[new URLSearchParams(request.search).get("tab") ?? ""] ?? []),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    const titles = () => screen.queryAllByTestId("content-card").map((card) => card.querySelector("span.truncate")?.textContent);

    expect(await screen.findByText("Taslak A")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Taslaklar" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("tab", { name: "Zamanlanan" }));
    await screen.findByText("Zamanlı B");
    expect(titles()).toEqual(["Zamanlı B", "Yolda C", "Tekrar H"]);

    await user.click(screen.getByRole("tab", { name: "Yayınlanan" }));
    await screen.findByText("Yayında D");
    expect(titles()).toEqual(["Yayında D"]);

    await user.click(screen.getByRole("tab", { name: "Sorunlar" }));
    await screen.findByText("Sorun E");
    expect(titles()).toEqual(["Sorun E", "Beklemede F", "Reddedilen I"]);
    expect(screen.queryByText("Vazgeçilen G")).toBeNull();

    const asked = requests.filter((r) => r.path === LIST_URL).map((r) => new URLSearchParams(r.search).get("tab"));
    expect(new Set(asked)).toEqual(new Set(["drafts", "scheduled", "published", "problems"]));
  });

  it("opens the tab named in the address", async () => {
    mockApi(
      routes({
        [`GET ${LIST_URL}`]: (request) =>
          page(
            new URLSearchParams(request.search).get("tab") === "problems"
              ? [contentItem({ title: "Sorun E", status: "failed" })]
              : [],
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content?tab=problems`);
    expect(await screen.findByText("Sorun E")).toBeInTheDocument();
    expect(screen.getByText("Başarısız")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sorunlar" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows an empty state that says which tab is empty", async () => {
    mockApi(routes({ [`GET ${LIST_URL}`]: () => page([]) }));
    renderApp(`/w/${WS_GOLKENT}/content?tab=problems`);
    expect(await screen.findByText("Sorun yok")).toBeInTheDocument();
  });

  it("explains a failed load from the error code", async () => {
    mockApi(routes({ [`GET ${LIST_URL}`]: () => problem(403, "FORBIDDEN") }));
    renderApp(`/w/${WS_GOLKENT}/content`);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("content editor: feed", () => {
  it("shows the caption with a counter and saves only what changed, with expected_version", async () => {
    const saved = contentItem({ version: 6, caption: "Yeni açıklama" });
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem({ version: 5 })),
        [`PATCH ${ITEM_URL}`]: () => json(saved),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const user = userEvent.setup();

    const caption = await screen.findByLabelText("Açıklama");
    expect(caption).toHaveValue("Aylık üyelik şimdi çok uygun!");
    expect(screen.getByTestId("caption-counter")).toHaveTextContent("29 / 2200");
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeDisabled();

    await user.clear(caption);
    await user.type(caption, "Yeni açıklama");
    expect(screen.getByTestId("caption-counter")).toHaveTextContent("13 / 2200");
    expect(screen.getByText("Kaydedilmemiş değişiklikler var")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText("Kaydedildi")).toBeInTheDocument();
    const sent = patches(requests);
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({ caption: "Yeni açıklama", expected_version: 5 });
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeDisabled();
  });

  it("turns the counter red and says so when the caption is too long", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem({ caption: "a".repeat(2201) })) }));
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const counter = await screen.findByTestId("caption-counter");
    expect(counter).toHaveTextContent("2201 / 2200: çok uzun");
  });

  it("reloads on a version conflict, keeps the typing and saves again with the new version", async () => {
    let current = contentItem({ version: 2, caption: "Sunucudaki ilk hali" });
    let conflictOnce = true;
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(current),
        [`PATCH ${ITEM_URL}`]: () => {
          if (conflictOnce) {
            conflictOnce = false;
            // Somebody else saved in between.
            current = contentItem({ version: 3, caption: "Başkasının yazdığı", title: "Başka başlık" });
            return problem(409, "VERSION_CONFLICT", { params: { expected: 2, current: 3 } });
          }
          return json(contentItem({ version: 4, caption: "Benim yazdığım", title: "Başka başlık" }));
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const user = userEvent.setup();

    const caption = await screen.findByLabelText("Açıklama");
    await user.clear(caption);
    await user.type(caption, "Benim yazdığım");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    const notice = await screen.findByTestId("version-conflict");
    expect(notice).toHaveTextContent("Siz düzenlerken başka biri bu içeriği değiştirdi");
    // The latest version was loaded (the title someone else changed) and the typing is still there.
    await waitFor(() => expect(screen.getByLabelText("Başlık")).toHaveValue("Başka başlık"));
    expect(screen.getByLabelText("Açıklama")).toHaveValue("Benim yazdığım");
    // No generic error box next to the specific message.
    expect(screen.queryByText("Siz çalışırken başka biri bunu değiştirdi.")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("Kaydedildi")).toBeInTheDocument();
    expect(screen.queryByTestId("version-conflict")).toBeNull();
    const sent = patches(requests);
    expect(sent.map((r) => (r.body as { expected_version: number }).expected_version)).toEqual([2, 3]);
  });

  it("warns that editing a scheduled item voids its approval", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem({ status: "scheduled" })) }));
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByTestId("voids-approval")).toHaveTextContent("onay geçersiz olur");
  });

  it.each(["publishing", "retry_scheduled", "published", "cancelled"] as const)(
    "does not let a %s item be edited",
    async (status) => {
      mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem({ status })) }));
      renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
      expect(await screen.findByTestId("content-readonly")).toHaveTextContent("artık değiştirilemez");
      expect(screen.queryByRole("button", { name: "Kaydet" })).toBeNull();
      expect(screen.queryByLabelText("Açıklama")).toBeNull();
    },
  );

  it("says 'Yayınlandı' on the detail page only for a published item", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem({ status: "scheduled" })) }));
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await screen.findByLabelText("Açıklama");
    expect(screen.getByText("Zamanlandı")).toBeInTheDocument();
    expect(screen.queryByText("Yayınlandı")).toBeNull();
  });

  it("says the content was not found for a foreign or unknown id", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => problem(404, "NOT_FOUND") }));
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByText("Bu içerik bulunamadı.")).toBeInTheDocument();
  });
});

describe("content editor: story", () => {
  const story = (overrides: Partial<ContentItem> = {}) =>
    contentItem({
      content_type: "story_image",
      caption: null,
      overlay_text_suggestions: ["İlk deneme dersi ücretsiz!"],
      ...overrides,
    });

  it("offers overlay suggestions and the note that the text goes on the image, but no caption", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(story({ version: 2 })),
        [`PATCH ${ITEM_URL}`]: () => json(story({ version: 3, overlay_text_suggestions: ["İlk ders bizden!"] })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const user = userEvent.setup();

    const first = await screen.findByLabelText("Öneri 1");
    expect(first).toHaveValue("İlk deneme dersi ücretsiz!");
    expect(screen.getByTestId("overlay-note")).toHaveTextContent("metin görselin üzerinde olmalı");
    expect(screen.queryByLabelText("Açıklama")).toBeNull();
    expect(screen.queryByTestId("caption-counter")).toBeNull();

    await user.clear(first);
    await user.type(first, "İlk ders bizden!");
    await user.click(screen.getByRole("button", { name: "Öneri ekle" }));
    expect(screen.getByLabelText("Öneri 2")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    await screen.findByText("Kaydedildi");
    // The empty second suggestion is not sent.
    expect(patches(requests)[0]!.body).toEqual({
      overlay_text_suggestions: ["İlk ders bizden!"],
      expected_version: 2,
    });
  });

  it("removes a suggestion", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(story({ overlay_text_suggestions: ["Bir", "İki"] })),
        [`PATCH ${ITEM_URL}`]: () => json(story({ version: 2, overlay_text_suggestions: ["İki"] })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const user = userEvent.setup();
    await screen.findByLabelText("Öneri 2");
    await user.click(screen.getByRole("button", { name: "Öneri 1 sil" }));
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await screen.findByText("Kaydedildi");
    expect(patches(requests)[0]!.body).toEqual({ overlay_text_suggestions: ["İki"], expected_version: 1 });
  });
});

describe("content editor: validation issues", () => {
  it("draws a value equal to a verified fact as a fact chip, not as an error", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            contentItem({
              caption: "Aylık üyelik 6.000 ₺ / ay",
              validation: {
                passed: true,
                stale: false,
                errors: [],
                warnings: [],
                issues: [
                  claimIssue({ text: "6.000 ₺ / ay", matches_verified: true, fact_key: "pricing.membership_monthly" }),
                ],
              },
            }),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const grounded = await screen.findByTestId("grounded-issue");
    expect(within(grounded).getByTestId("fact-chip")).toHaveTextContent("6.000 ₺ / ay");
    expect(grounded).toHaveTextContent("doğrulanmış bilginizle eşleşiyor");
    expect(screen.queryByTestId("blocking-issue")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();

    // Tapping the chip names the fact it comes from (label and version from the knowledge base).
    await userEvent.setup().click(within(grounded).getByTestId("fact-chip"));
    const source = await within(grounded).findByRole("status");
    expect(source).toHaveTextContent("Aylık üyelik");
    expect(source).toHaveTextContent("sürüm 1");
  });

  it("shows a value that matches no verified fact as a blocking issue with a way out", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            contentItem({
              caption: "Aylık üyelik 5.000 ₺ / ay",
              validation: { passed: false, stale: false, errors: [], warnings: [], issues: [claimIssue()] },
            }),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const blocking = await screen.findByTestId("blocking-issue");
    expect(blocking).toHaveTextContent("“5.000 ₺ / ay” doğrulanmış bir bilgi değil");
    expect(screen.queryByTestId("grounded-issue")).toBeNull();
    expect(screen.getByText("Bunlar düzeltilmeden yayına gönderilemez.")).toBeInTheDocument();
  });

  it("tells a left-over {{fact:key}} placeholder apart from a wrong value", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            contentItem({
              caption: "Fiyat {{fact:pricing.membership_monthly}}",
              validation: {
                passed: false,
                stale: false,
                errors: [],
                warnings: [],
                issues: [
                  claimIssue({
                    code: "PLACEHOLDER_UNRENDERED",
                    text: "{{fact:pricing.membership_monthly}}",
                    fact_key: "pricing.membership_monthly",
                  }),
                ],
              },
            }),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const blocking = await screen.findByTestId("blocking-issue");
    expect(blocking).toHaveAttribute("data-code", "PLACEHOLDER_UNRENDERED");
    expect(blocking).toHaveTextContent("yer tutucusu doldurulamadı");
  });

  it("hides the issues of a text that has unsaved edits (their positions no longer apply)", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(contentItem({ validation: { passed: false, stale: false, errors: [], warnings: [], issues: [claimIssue()] } })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await screen.findByTestId("blocking-issue");
    await userEvent.setup().type(screen.getByLabelText("Açıklama"), "!");
    expect(screen.queryByTestId("blocking-issue")).toBeNull();
  });

  it("runs the pre-publish check and lists what must be fixed", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem()),
        [`POST ${ITEM_URL}/validate`]: () =>
          json({
            passed: true,
            issues: [],
            stale: false,
            errors: [
              { code: "CONTENT_MEDIA_REQUIRED", field: "media_asset_id", params: {} },
              { code: "SOMETHING_NEW", field: null, params: {}, message: "Sunucunun kendi mesajı" },
            ],
            warnings: [],
          }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Yayın öncesi kontrol" }));
    const checks = await screen.findByTestId("checks");
    expect(within(checks).getByText("Bir görsel ekleyin.")).toBeInTheDocument();
    expect(within(checks).getByText("Sunucunun kendi mesajı")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "POST" && r.path === `${ITEM_URL}/validate`)).toBe(true);
  });
});

describe("content generation", () => {
  it("shows that the draft is being prepared and fills in when the job has saved it", async () => {
    let done = false;
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            done
              ? contentItem({ version: 2, caption: "Yapay zekanın yazdığı metin", generation: { status: "succeeded", error_code: null } })
              : contentItem({ caption: null, generation: { status: "running", error_code: null } }),
          ),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);

    expect(await screen.findByTestId("generation-running")).toHaveTextContent("Hazırlanıyor…");
    // Writing by hand stays possible meanwhile.
    expect(screen.getByLabelText("Açıklama")).toHaveValue("");
    done = true;
    await waitFor(() => expect(screen.queryByTestId("generation-running")).toBeNull(), { timeout: 6000 });
    expect(screen.getByLabelText("Açıklama")).toHaveValue("Yapay zekanın yazdığı metin");
  }, 10_000);

  it("leaves a manual draft with a note when generation failed", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(contentItem({ caption: null, generation: { status: "failed", error_code: "LLM_UNAVAILABLE" } })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByTestId("generation-failed")).toHaveTextContent("kendiniz yazabilirsiniz");
    expect(screen.queryByTestId("generation-running")).toBeNull();
    expect(screen.getByLabelText("Açıklama")).toBeEnabled();
  });

  it("marks a card whose draft is still being prepared", async () => {
    mockApi(
      routes({
        [`GET ${LIST_URL}`]: () =>
          page([contentItem({ caption: null, generation: { status: "queued", error_code: null } })]),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    expect(await screen.findByTestId("card-generating")).toHaveTextContent("Hazırlanıyor…");
  });
});

describe("media upload", () => {
  const jpeg = () => new File(["fake-image-bytes"], "foto.jpg", { type: "image/jpeg" });
  const fileInput = () => screen.getByTestId("media-upload").querySelector("input[type=file]") as HTMLInputElement;
  const image = () => new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { headers: { "content-type": "image/jpeg" } });

  it("uploads, attaches the image with expected_version, shows the authenticated preview and the check warnings", async () => {
    let attached = false;
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            contentItem({
              content_type: "story_image",
              caption: null,
              version: attached ? 2 : 1,
              media_asset_id: attached ? MEDIA_ID : null,
            }),
          ),
        [`POST ${BASE}/media`]: () => json(mediaAsset({ width: 1000, height: 1000 }), 201),
        [`PATCH ${ITEM_URL}`]: () => {
          attached = true;
          return json(contentItem({ content_type: "story_image", caption: null, version: 2, media_asset_id: MEDIA_ID }));
        },
        [`POST ${ITEM_URL}/validate`]: () =>
          json({
            passed: true,
            issues: [],
            stale: false,
            errors: [],
            warnings: [
              { code: "STORY_ASPECT_NOT_9_16", field: "media_asset_id", params: { width: 1000, height: 1000 } },
            ],
          }),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    const user = userEvent.setup();

    await screen.findByTestId("media-upload");
    expect(screen.getByText(/Story için 9:16 bir görsel ekleyin/)).toBeInTheDocument();
    const append = vi.spyOn(FormData.prototype, "append");
    const file = jpeg();
    await user.upload(fileInput(), file);
    // The file goes out as the multipart field "file".
    expect(append).toHaveBeenCalledWith("file", file);
    append.mockRestore();

    expect((await screen.findByAltText("Seçilen görselin önizlemesi")).getAttribute("src")).toMatch(/^blob:/);
    const upload = requests.find((r) => r.method === "POST" && r.path === `${BASE}/media`);
    expect(upload).toBeDefined();
    expect(upload!.headers.get("content-type")).toMatch(/^multipart\/form-data/);
    expect(patches(requests)[0]!.body).toEqual({ media_asset_id: MEDIA_ID, expected_version: 1 });
    const warnings = await screen.findByTestId("media-warnings");
    expect(warnings).toHaveTextContent("Görsel 9:16 değil (1000×1000)");
    expect(screen.getByText("1000 × 1000 piksel")).toBeInTheDocument();
    // The preview came through the authenticated endpoint, with the session cookie.
    expect(requests.some((r) => r.method === "GET" && r.path === `${BASE}/media/${MEDIA_ID}/content`)).toBe(true);
  });

  it("maps MEDIA_INVALID to the reason the server gave", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem()),
        [`POST ${BASE}/media`]: () => problem(422, "MEDIA_INVALID", { params: { reason: "CORRUPT_IMAGE" } }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await screen.findByTestId("media-upload");
    await userEvent.setup().upload(fileInput(), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent("Görsel dosyası bozuk görünüyor");
  });

  it("falls back to the shared message for a MEDIA_INVALID without a known reason", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem()),
        [`POST ${BASE}/media`]: () => problem(422, "MEDIA_INVALID"),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await screen.findByTestId("media-upload");
    await userEvent.setup().upload(fileInput(), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu dosya desteklenen bir görsel değil.");
  });

  it("maps MEDIA_TOO_LARGE and names the limit", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem()),
        [`POST ${BASE}/media`]: () => problem(413, "MEDIA_TOO_LARGE", { params: { limit_bytes: 8 * 1024 * 1024 } }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    await screen.findByTestId("media-upload");
    await userEvent.setup().upload(fileInput(), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu görsel çok büyük (sınır 8 MB)");
  });

  it("keeps the current image and attaches nothing when the upload fails", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem({ media_asset_id: MEDIA_ID })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        [`POST ${BASE}/media`]: () => problem(422, "MEDIA_INVALID", { params: { reason: "NOT_AN_IMAGE" } }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByAltText("Seçilen görselin önizlemesi")).toBeInTheDocument();
    await userEvent.setup().upload(fileInput(), jpeg());
    expect(await screen.findByRole("alert")).toHaveTextContent("desteklenen bir görsel değil");
    expect(screen.getByAltText("Seçilen görselin önizlemesi")).toBeInTheDocument();
    expect(patches(requests)).toHaveLength(0);
  });

  it("says when the preview cannot be loaded", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem({ media_asset_id: MEDIA_ID })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: () => problem(404, "NOT_FOUND"),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByText("Görsel gösterilemedi.")).toBeInTheDocument();
  });

  it("says so in the editor too when the image of an editable item was deleted", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(contentItem({ media_asset_id: MEDIA_ID, media_deleted: true })),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByTestId("media-deleted")).toHaveTextContent("Görsel saklama süresi dolduğu için silindi.");
    expect(requests.some((r) => r.path === `${BASE}/media/${MEDIA_ID}/content`)).toBe(false);
  });

  it("says the image was deleted when its retention ended, and does not ask for the file", async () => {
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(contentItem({ status: "published", media_asset_id: MEDIA_ID, media_deleted: true })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: () => problem(404, "NOT_FOUND"),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content/${CONTENT_ID}`);
    expect(await screen.findByTestId("media-deleted")).toHaveTextContent(
      "Görsel saklama süresi dolduğu için silindi.",
    );
    expect(screen.queryByAltText("Seçilen görselin önizlemesi")).not.toBeInTheDocument();
    expect(screen.queryByText("Görsel gösterilemedi.")).not.toBeInTheDocument();
    expect(requests.some((r) => r.path === `${BASE}/media/${MEDIA_ID}/content`)).toBe(false);
  });
});
