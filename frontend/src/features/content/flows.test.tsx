import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ContentItem, ContentStatus, Me } from "@/api/types";
import { CONTENT_ID, MEDIA_ID, claimIssue, contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { SUBMIT_ITEM_CODES } from "./messages";
import { localToInstant, toLocalFields } from "./schedule";

afterEach(() => vi.unstubAllGlobals());

const TZ = "Europe/Istanbul";
const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const LIST_URL = `${BASE}/content-items`;
const ITEM_URL = `${LIST_URL}/${CONTENT_ID}`;
const ITEM_PAGE = `/w/${WS_GOLKENT}/content/${CONTENT_ID}`;

type Handlers = Record<string, (request: RecordedRequest) => Response>;

function me(role: "owner" | "manager" | "staff"): Me {
  return {
    ...ME,
    memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role } : m)),
  };
}

function routes(extra: Handlers = {}, role: "owner" | "manager" | "staff" = "owner"): Handlers {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(me(role)),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [fact()] }),
    [`GET ${BASE}/social-accounts`]: () => json({ items: [socialAccount()], next_cursor: null }),
    [`GET ${LIST_URL}`]: () => json({ items: [], next_cursor: null }),
    ...extra,
  };
}

const posts = (requests: RecordedRequest[], path: string) =>
  requests.filter((r) => r.method === "POST" && r.path === path);

/** A local date and time `minutes` from now on the workspace clock, as the inputs hold them. */
const inMinutes = (minutes: number) => toLocalFields(new Date(Date.now() + minutes * 60_000), TZ);

function setSchedule(date: string, time: string) {
  fireEvent.change(screen.getByLabelText("Tarih"), { target: { value: date } });
  fireEvent.change(screen.getByLabelText("Saat"), { target: { value: time } });
}

const draftWithMedia = (overrides: Partial<ContentItem> = {}) =>
  contentItem({ media_asset_id: MEDIA_ID, caption: "Aylık üyelik şimdi çok uygun!", ...overrides });

const image = () => new Response(new Blob(["jpeg"], { type: "image/jpeg" }), { headers: { "content-type": "image/jpeg" } });

async function openSchedule(item: ContentItem, extra: Handlers = {}, role: "owner" | "manager" | "staff" = "owner") {
  const requests = mockApi(
    routes(
      {
        [`GET ${ITEM_URL}`]: () => json(item),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        ...extra,
      },
      role,
    ),
  );
  renderApp(ITEM_PAGE);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Zamanla" }));
  const dialog = await screen.findByRole("dialog", { name: "Zamanla" });
  return { requests, user, dialog };
}

describe("new content: ask for a draft or start blank", () => {
  it("sends a generation request with a client_request_id and shows it running", async () => {
    const queued = contentItem({
      title: "Deneme dersi için story",
      content_type: "story_image",
      caption: null,
      generation: { status: "queued", error_code: null },
    });
    const requests = mockApi(
      routes({
        [`POST ${LIST_URL}/generate`]: () => json(queued, 202),
        [`GET ${ITEM_URL}`]: () => json({ ...queued, generation: { status: "running", error_code: null } }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Taslak iste" }));
    const dialog = await screen.findByRole("dialog", { name: "Yeni içerik" });
    await user.click(within(dialog).getByLabelText("Story"));
    await user.type(within(dialog).getByLabelText("Ne paylaşmak istiyorsunuz?"), "Deneme dersi için story");
    expect(await within(dialog).findByText("@golkent.fitness")).toBeInTheDocument();
    expect(within(dialog).getByTestId("simulated-badge")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Taslağı hazırla" }));

    const progress = await within(dialog).findByTestId("generation-progress");
    expect(progress).toHaveTextContent("Hazırlanıyor…");
    const body = posts(requests, `${LIST_URL}/generate`)[0]!.body as Record<string, unknown>;
    expect(body).toMatchObject({ content_type: "story_image", objective: "Deneme dersi için story", notes: null });
    expect(typeof body.client_request_id).toBe("string");
    expect((body.client_request_id as string).length).toBeGreaterThan(0);
  });

  it("when the AI fails it says so and leaves the manual draft to open", async () => {
    const queued = contentItem({ title: "Hafta sonu kampanyası", caption: null, generation: { status: "queued", error_code: null } });
    const failed = { ...queued, generation: { status: "failed" as const, error_code: "LLM_UNAVAILABLE" } };
    mockApi(
      routes({
        [`POST ${LIST_URL}/generate`]: () => json(queued, 202),
        [`GET ${ITEM_URL}`]: () => json(failed),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Taslak iste" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Ne paylaşmak istiyorsunuz?"), "Hafta sonu kampanyası");
    await user.click(within(dialog).getByRole("button", { name: "Taslağı hazırla" }));

    const progress = await within(dialog).findByText("Taslak otomatik hazırlanamadı.");
    expect(progress).toBeInTheDocument();
    // The cause comes from the error catalog and the fallback is stated plainly.
    expect(within(dialog).getByText("Yapay zekâ hizmetine şu anda ulaşılamıyor.")).toBeInTheDocument();
    expect(within(dialog).getByText("Boş bir taslak oluşturuldu. Metni kendiniz yazabilirsiniz.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Taslağı aç" }));
    // The draft is there to be written by hand: the editor is open and the page repeats what happened.
    expect(await screen.findByTestId("generation-failed")).toBeInTheDocument();
    expect(screen.getByLabelText("Açıklama")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a retry of the same brief keeps the client_request_id, a changed brief gets a new one", async () => {
    const queued = contentItem({ caption: null, generation: { status: "queued", error_code: null } });
    let calls = 0;
    const requests = mockApi(
      routes({
        [`POST ${LIST_URL}/generate`]: () => (calls++ < 2 ? problem(500, "INTERNAL_ERROR") : json(queued, 202)),
        [`GET ${ITEM_URL}`]: () => json(queued),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Taslak iste" }));
    const dialog = await screen.findByRole("dialog");
    const objective = within(dialog).getByLabelText("Ne paylaşmak istiyorsunuz?");
    await user.type(objective, "Yaz kampanyası");
    const submit = within(dialog).getByRole("button", { name: "Taslağı hazırla" });
    await user.click(submit);
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    await user.click(submit);
    await waitFor(() => expect(posts(requests, `${LIST_URL}/generate`)).toHaveLength(2));
    await user.type(objective, " 2");
    await user.click(submit);
    await waitFor(() => expect(posts(requests, `${LIST_URL}/generate`)).toHaveLength(3));

    const ids = posts(requests, `${LIST_URL}/generate`).map((r) => (r.body as { client_request_id: string }).client_request_id);
    expect(ids[0]).toBe(ids[1]);
    expect(ids[2]).not.toBe(ids[0]);
  });

  it("offers a blank draft that is written by hand, with no AI involved", async () => {
    const created = contentItem({ title: "Salı duyurusu", caption: null });
    const requests = mockApi(
      routes({
        [`POST ${LIST_URL}`]: () => json(created, 201),
        [`GET ${ITEM_URL}`]: () => json(created),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Boş taslak" }));
    const dialog = await screen.findByRole("dialog", { name: "Yeni içerik" });
    expect(within(dialog).queryByLabelText("Ne paylaşmak istiyorsunuz?")).toBeNull();
    const create = within(dialog).getByRole("button", { name: "Boş taslak oluştur" });
    expect(create).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Başlık"), "Salı duyurusu");
    await user.click(create);

    // It opens in the editor.
    expect(await screen.findByRole("heading", { name: "Salı duyurusu" })).toBeInTheDocument();
    expect(screen.getByLabelText("Açıklama")).toBeInTheDocument();
    const body = posts(requests, LIST_URL)[0]!.body as Record<string, unknown>;
    expect(body).toMatchObject({ content_type: "feed_image", title: "Salı duyurusu" });
    expect(typeof body.client_request_id).toBe("string");
    expect(requests.some((r) => r.path.endsWith("/generate"))).toBe(false);
  });
});

describe("schedule sheet: who can publish now", () => {
  it("staff never see 'Hemen yayınla'; they send for approval", async () => {
    const submitted = draftWithMedia({ status: "pending_approval", version: 1 });
    const { requests, user, dialog } = await openSchedule(
      draftWithMedia(),
      { [`POST ${ITEM_URL}/submit`]: () => json(submitted) },
      "staff",
    );
    expect(within(dialog).queryByText(/Hemen yayınla/)).toBeNull();
    expect(within(dialog).queryByRole("radio")).toBeNull();
    expect(within(dialog).queryByRole("button", { name: /Onayla ve/ })).toBeNull();
    expect(within(dialog).getByTestId("timezone-label")).toHaveTextContent("İstanbul saati");
    const send = within(dialog).getByRole("button", { name: "Onaya gönder" });

    const when = inMinutes(24 * 60 + 5);
    setSchedule(when.date, "19:00");
    await user.click(send);

    await waitFor(() => expect(posts(requests, `${ITEM_URL}/submit`)).toHaveLength(1));
    expect(posts(requests, `${ITEM_URL}/submit`)[0]!.body).toEqual({
      schedule: { local_date: when.date, local_time: "19:00" },
      self_approve: false,
      expected_version: 1,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("staff choosing a time less than 15 minutes ahead get the approval message and cannot send", async () => {
    const { requests, user, dialog } = await openSchedule(draftWithMedia(), {}, "staff");
    const soon = inMinutes(5);
    setSchedule(soon.date, soon.time);

    const precheck = await within(dialog).findByTestId("schedule-precheck");
    expect(precheck).toHaveAttribute("data-code", "SCHEDULE_TOO_SOON_FOR_APPROVAL");
    expect(precheck).toHaveTextContent("Yayından önce birinin onaylaması gerekir. Şu andan en az 15 dakika sonrasını seçin.");
    const send = within(dialog).getByRole("button", { name: "Onaya gönder" });
    expect(send).toBeDisabled();
    await user.click(send);
    expect(posts(requests, `${ITEM_URL}/submit`)).toHaveLength(0);
  });

  it("an owner sees both the 'now' choice and 'Onayla ve zamanla'", async () => {
    const { dialog } = await openSchedule(draftWithMedia());
    expect(within(dialog).getByRole("radio", { name: "Hemen yayınla" })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: "Belirli bir zamanda" })).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "Onayla ve zamanla" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Onaya gönder" })).toBeNull();
  });

  it("a manager is an approver too", async () => {
    const { dialog } = await openSchedule(draftWithMedia(), {}, "manager");
    expect(within(dialog).getByRole("radio", { name: "Hemen yayınla" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Onayla ve zamanla" })).toBeInTheDocument();
  });

  it("'now' is sent as the schedule 'now', self-approved, and the item reads Zamanlandı (not published)", async () => {
    let submitted = false;
    const scheduled = draftWithMedia({ status: "scheduled", version: 1, scheduled_at: new Date().toISOString() });
    const { requests, user, dialog } = await openSchedule(draftWithMedia(), {
      [`POST ${ITEM_URL}/submit`]: () => {
        submitted = true;
        return json(scheduled);
      },
      [`GET ${ITEM_URL}`]: () => json(submitted ? scheduled : draftWithMedia()),
    });
    await user.click(within(dialog).getByRole("radio", { name: "Hemen yayınla" }));
    expect(within(dialog).queryByLabelText("Saat")).toBeNull();
    expect(within(dialog).getByTestId("summary-when")).toHaveTextContent("Hemen");
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve hemen yayınla" }));

    await waitFor(() => expect(posts(requests, `${ITEM_URL}/submit`)).toHaveLength(1));
    expect(posts(requests, `${ITEM_URL}/submit`)[0]!.body).toEqual({
      schedule: "now",
      self_approve: true,
      expected_version: 1,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByText("Zamanlandı")).toBeInTheDocument();
    expect(screen.queryByText("Yayınlandı")).toBeNull();
  });

  it("sends the owner's wall-clock time, which is 16:00 UTC for 19:00 in Istanbul", async () => {
    const { requests, user, dialog } = await openSchedule(draftWithMedia({ version: 4 }), {
      [`POST ${ITEM_URL}/submit`]: () => json(draftWithMedia({ status: "scheduled", version: 4 })),
    });
    const day = inMinutes(48 * 60).date;
    setSchedule(day, "19:00");
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve zamanla" }));

    await waitFor(() => expect(posts(requests, `${ITEM_URL}/submit`)).toHaveLength(1));
    const body = posts(requests, `${ITEM_URL}/submit`)[0]!.body as {
      schedule: { local_date: string; local_time: string };
      self_approve: boolean;
      expected_version: number;
    };
    expect(body).toEqual({ schedule: { local_date: day, local_time: "19:00" }, self_approve: true, expected_version: 4 });
    // The server converts that wall-clock time; the same conversion gives the UTC instant it stores.
    const instant = localToInstant(body.schedule.local_date, body.schedule.local_time, TZ)!;
    expect(instant.toISOString()).toBe(`${day}T16:00:00.000Z`);
  });

  it("summarises exactly what will be posted and when, in the workspace timezone", async () => {
    const { dialog, user } = await openSchedule(
      draftWithMedia({ caption: "Hafta sonu dersleri ücretsiz değil, ama güzel!" }),
    );
    const day = inMinutes(48 * 60).date;
    setSchedule(day, "19:00");
    const summary = within(dialog).getByTestId("schedule-summary");
    expect(within(summary).getByText("Gönderi")).toBeInTheDocument();
    expect(await within(summary).findByText("@golkent.fitness")).toBeInTheDocument();
    expect(within(summary).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(within(summary).getByTestId("summary-when")).toHaveTextContent("19:00 (İstanbul saati)");
    expect(within(summary).getByTestId("preview-caption")).toHaveTextContent(
      "Hafta sonu dersleri ücretsiz değil, ama güzel!",
    );
    expect(await within(summary).findByTestId("preview-media")).toHaveAttribute("src", expect.stringMatching(/^blob:/));
    await user.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a story summary shows the overlay text and says it is not published separately", async () => {
    const { dialog } = await openSchedule(
      draftWithMedia({ content_type: "story_image", caption: null, overlay_text_suggestions: ["İlk ders bizden", "Yarın 19:00"] }),
    );
    const items = within(dialog).getAllByTestId("preview-overlay-item");
    expect(items.map((li) => li.textContent)).toEqual(["İlk ders bizden", "Yarın 19:00"]);
    expect(within(dialog).getByText(/ayrıca yayınlanmaz/)).toBeInTheDocument();
    expect(within(dialog).queryByTestId("preview-caption")).toBeNull();
  });
});

describe("schedule sheet: every submit item code reaches the screen (G17)", () => {
  const PARAMS: Record<string, Record<string, unknown>> = {
    MEDIA_NOT_READY: { status: "processing" },
    CAPTION_TOO_LONG: { length: 2300, max: 2200 },
    ASPECT_RATIO_OUT_OF_RANGE: { width: 4000, height: 1000 },
    SCHEDULE_TIME_NONEXISTENT: { local_date: "2026-03-29", local_time: "03:30", timezone: "Europe/Istanbul" },
    SCHEDULE_TOO_SOON_FOR_APPROVAL: { minutes: 15 },
    CAPABILITY_MISSING: { capability: "publish_feed_image" },
    STORY_ASPECT_NOT_9_16: { width: 1000, height: 1000 },
  };
  const TEXT: Record<string, string> = {
    CONTENT_MEDIA_REQUIRED: "Bir görsel ekleyin.",
    MEDIA_NOT_READY: "Görsel henüz hazır değil.",
    CAPTION_REQUIRED: "Bir açıklama yazın.",
    CAPTION_TOO_LONG: "Açıklama çok uzun (2300 / 2200 karakter).",
    CAPTION_NOT_ALLOWED: "Story'nin açıklaması olmaz.",
    ASPECT_RATIO_OUT_OF_RANGE: "Görselin oranı gönderi için uygun değil",
    CLAIM_VALIDATION_FAILED: "Metinde doğrulanmamış bilgiler var.",
    SCHEDULE_IN_PAST: "Seçtiğiniz zaman geçmişte.",
    SCHEDULE_TOO_FAR: "En fazla 60 gün sonrasına zamanlanabilir.",
    SCHEDULE_TIME_NONEXISTENT: "İstanbul saati için 2026-03-29 günü saat 03:30 diye bir saat yok",
    SCHEDULE_TOO_SOON_FOR_APPROVAL: "Şu andan en az 15 dakika sonrasını seçin.",
    ACCOUNT_NOT_CONNECTED: "Bağlı bir Instagram hesabı yok.",
    CAPABILITY_MISSING: "Bağlı hesap bu içerik türünü yayınlayamıyor.",
    PUBLISH_QUOTA_FORECAST_EXCEEDED: "Bu saatin çevresinde zaten çok fazla gönderi zamanlanmış.",
    STORY_ASPECT_NOT_9_16: "Görsel 9:16 değil (1000×1000).",
    OVERLAY_TOO_LONG: "Bu öneri uzun",
  };
  const WARNINGS = ["STORY_ASPECT_NOT_9_16", "OVERLAY_TOO_LONG"];
  const ERRORS = SUBMIT_ITEM_CODES.filter((code) => !WARNINGS.includes(code));
  const SCHEDULE_AREA = new Set([
    "SCHEDULE_IN_PAST",
    "SCHEDULE_TOO_FAR",
    "SCHEDULE_TIME_NONEXISTENT",
    "SCHEDULE_TOO_SOON_FOR_APPROVAL",
    "PUBLISH_QUOTA_FORECAST_EXCEEDED",
  ]);

  it("covers all fourteen error codes and both warnings", () => {
    expect(ERRORS).toHaveLength(14);
    expect(WARNINGS).toHaveLength(2);
  });

  it.each(ERRORS)("%s is shown as an inline message", async (code) => {
    const item = (field: string | null) => ({ code, field, params: PARAMS[code] ?? {}, message: "server text" });
    const { user, dialog } = await openSchedule(draftWithMedia(), {
      [`POST ${ITEM_URL}/submit`]: () =>
        problem(422, "CONTENT_VALIDATION_FAILED", {
          errors: [
            code === "CLAIM_VALIDATION_FAILED"
              ? { ...item(null), params: { issues: [claimIssue({ text: "5.000 ₺ / ay" })] } }
              : item("x"),
          ],
          params: { warnings: [] },
        }),
    });
    setSchedule(inMinutes(48 * 60).date, "19:00");
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve zamanla" }));

    const shown = await within(dialog).findByTestId(SCHEDULE_AREA.has(code) ? "schedule-errors" : "submit-problems");
    const row = shown.querySelector(`[data-code="${code}"]`);
    expect(row, code).not.toBeNull();
    expect(row!.textContent).toContain(TEXT[code]);
    if (code === "CLAIM_VALIDATION_FAILED") {
      // The value that is not a verified fact is named, and the way to the text is offered.
      expect(within(dialog).getByTestId("claim-issue")).toHaveTextContent("“5.000 ₺ / ay” doğrulanmış bir bilgi değil.");
      expect(within(dialog).getByRole("button", { name: "Metni düzenle" })).toBeInTheDocument();
    }
    // Nothing was written; the sheet stays open so the owner can fix it.
    expect(screen.getByRole("dialog", { name: "Zamanla" })).toBeInTheDocument();
  });

  it.each(WARNINGS)("%s (a warning) is shown without blocking", async (code) => {
    const { user, dialog } = await openSchedule(draftWithMedia(), {
      [`POST ${ITEM_URL}/submit`]: () =>
        problem(422, "CONTENT_VALIDATION_FAILED", {
          errors: [{ code: "CAPTION_REQUIRED", field: "caption", params: {} }],
          params: { warnings: [{ code, field: "media_asset_id", params: PARAMS[code] ?? {}, message: "server text" }] },
        }),
    });
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve zamanla" }));
    const warnings = await within(dialog).findByTestId("submit-warnings");
    expect(warnings.querySelector(`[data-code="${code}"]`)!.textContent).toContain(TEXT[code]);
    expect(within(dialog).getByTestId("submit-problems")).toHaveTextContent("Bir açıklama yazın.");
  });

  it("shows several problems at once, schedule ones by the time fields", async () => {
    const { user, dialog } = await openSchedule(draftWithMedia(), {
      [`POST ${ITEM_URL}/submit`]: () =>
        problem(422, "CONTENT_VALIDATION_FAILED", {
          errors: [
            { code: "CONTENT_MEDIA_REQUIRED", field: "media_asset_id", params: {} },
            { code: "SCHEDULE_TOO_FAR", field: "schedule", params: {} },
          ],
          params: { warnings: [] },
        }),
    });
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve zamanla" }));
    expect(await within(dialog).findByTestId("schedule-errors")).toHaveTextContent("En fazla 60 gün");
    expect(within(dialog).getByTestId("submit-problems")).toHaveTextContent("Bir görsel ekleyin.");
  });

  it("a time in a clock gap is caught before sending and named with the zone (SCHEDULE_TIME_NONEXISTENT)", async () => {
    // Lisbon, 28 March 2027: the clocks jump from 01:00 to 02:00.
    const { requests, user, dialog } = await openSchedule(draftWithMedia(), {
      [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT, { timezone: "Europe/Lisbon" })),
    });
    setSchedule("2027-03-28", "01:30");
    const precheck = await within(dialog).findByTestId("schedule-precheck");
    expect(precheck).toHaveAttribute("data-code", "SCHEDULE_TIME_NONEXISTENT");
    expect(precheck).toHaveTextContent("Lisbon saati için 2027-03-28 günü saat 01:30 diye bir saat yok");
    const send = within(dialog).getByRole("button", { name: "Onayla ve zamanla" });
    expect(send).toBeDisabled();
    await user.click(send);
    expect(posts(requests, `${ITEM_URL}/submit`)).toHaveLength(0);
  });

  it("explains a version conflict and reloads the item", async () => {
    const { requests, user, dialog } = await openSchedule(draftWithMedia(), {
      [`POST ${ITEM_URL}/submit`]: () => problem(409, "VERSION_CONFLICT"),
    });
    const before = requests.filter((r) => r.method === "GET" && r.path === ITEM_URL).length;
    await user.click(within(dialog).getByRole("button", { name: "Onayla ve zamanla" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Siz çalışırken başka biri bunu değiştirdi.");
    await waitFor(() =>
      expect(requests.filter((r) => r.method === "GET" && r.path === ITEM_URL).length).toBeGreaterThan(before),
    );
  });
});

describe("on hold", () => {
  const held = (reason: string, overrides: Partial<ContentItem> = {}) =>
    draftWithMedia({
      status: "on_hold",
      version: 3,
      hold_reason: reason,
      scheduled_at: "2026-10-21T16:00:00Z",
      ...overrides,
    });

  it("FACT_CHANGED: says why and offers edit, approve again as it is, and cancel", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(held("FACT_CHANGED")), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }));
    renderApp(ITEM_PAGE);
    const panel = await screen.findByTestId("on-hold");
    expect(panel).toHaveAttribute("data-reason", "FACT_CHANGED");
    expect(panel).toHaveTextContent("Kullandığı işletme bilgisi değiştiği için beklemeye alındı.");
    expect(within(panel).getByRole("link", { name: "İşletme bilgilerini aç" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/knowledge`,
    );
    expect(within(panel).getByRole("button", { name: "Düzenle" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Olduğu gibi yeniden onayla" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "İptal et" })).toBeInTheDocument();
    expect(document.querySelector('[data-status="on_hold"]')).toHaveTextContent("Beklemede");
  });

  it("ACCOUNT_UNAVAILABLE: points at the connection instead", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(held("ACCOUNT_UNAVAILABLE")), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }));
    renderApp(ITEM_PAGE);
    const panel = await screen.findByTestId("on-hold");
    expect(panel).toHaveAttribute("data-reason", "ACCOUNT_UNAVAILABLE");
    expect(panel).toHaveTextContent("Instagram hesabı kullanılamadığı için beklemeye alındı.");
    expect(within(panel).getByRole("link", { name: "Bağlantıyı kontrol et" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/automation`,
    );
    expect(within(panel).queryByRole("link", { name: "İşletme bilgilerini aç" })).toBeNull();
    expect(within(panel).getByRole("button", { name: "Olduğu gibi yeniden onayla" })).toBeInTheDocument();
  });

  it("staff can only edit a held item (no re-approve, no cancel)", async () => {
    mockApi(
      routes(
        { [`GET ${ITEM_URL}`]: () => json(held("FACT_CHANGED", { can_cancel: false })), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image },
        "staff",
      ),
    );
    renderApp(ITEM_PAGE);
    const panel = await screen.findByTestId("on-hold");
    expect(within(panel).getByRole("button", { name: "Düzenle" })).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Olduğu gibi yeniden onayla" })).toBeNull();
    expect(within(panel).queryByRole("button", { name: "İptal et" })).toBeNull();
    expect(panel).toHaveTextContent("Yeniden onay için bir sahip ya da yönetici gerekir.");
  });

  it("Düzenle moves to the text", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(held("FACT_CHANGED")), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }));
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(within(await screen.findByTestId("on-hold")).getByRole("button", { name: "Düzenle" }));
    expect(screen.getByLabelText("Başlık")).toHaveFocus();
  });

  it("re-approval sends the schedule and the version, and the item comes back with the next version", async () => {
    let approved = false;
    const scheduled = held("FACT_CHANGED", { status: "scheduled", version: 4, hold_reason: null });
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(approved ? scheduled : held("FACT_CHANGED")),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        [`POST ${ITEM_URL}/reapprove`]: () => {
          approved = true;
          return json(scheduled);
        },
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Olduğu gibi yeniden onayla" }));
    const dialog = await screen.findByRole("dialog", { name: "Yeniden onayla ve zamanla" });
    const day = inMinutes(72 * 60).date;
    setSchedule(day, "10:30");
    await user.click(within(dialog).getByRole("button", { name: "Yeniden onayla ve zamanla" }));

    await waitFor(() => expect(posts(requests, `${ITEM_URL}/reapprove`)).toHaveLength(1));
    expect(posts(requests, `${ITEM_URL}/reapprove`)[0]!.body).toEqual({
      schedule: { local_date: day, local_time: "10:30" },
      expected_version: 3,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByText("Zamanlandı")).toBeInTheDocument();
    expect(screen.queryByTestId("on-hold")).toBeNull();
  });

  it("re-approval that fails the claim check shows the old price and leads to the editor", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(held("FACT_CHANGED", { caption: "Aylık üyelik 6.000 ₺ / ay" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        [`POST ${ITEM_URL}/reapprove`]: () =>
          problem(422, "CONTENT_VALIDATION_FAILED", {
            errors: [
              {
                code: "CLAIM_VALIDATION_FAILED",
                field: null,
                params: { issues: [claimIssue({ text: "6.000 ₺ / ay", matches_verified: false })] },
              },
            ],
            params: { warnings: [] },
          }),
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Olduğu gibi yeniden onayla" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Yeniden onayla ve zamanla" }));

    expect(await within(dialog).findByTestId("claim-issue")).toHaveTextContent("“6.000 ₺ / ay” doğrulanmış bir bilgi değil.");
    await user.click(within(dialog).getByRole("button", { name: "Metni düzenle" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(screen.getByLabelText("Başlık")).toHaveFocus());
  });

  it("a draft sent back by a fact change or an expired approval says so", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(contentItem({ status: "draft", hold_reason: "APPROVAL_EXPIRED" })) }));
    renderApp(ITEM_PAGE);
    expect(await screen.findByTestId("draft-hold")).toHaveTextContent("Onay süresi dolduğu için taslağa döndü.");
  });
});

describe("failure detail", () => {
  it("a failed post says what happened and what to do, that nothing more is tried, and offers edit and resend", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "failed", last_error_code: "MEDIA_REJECTED" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    const detail = await screen.findByTestId("failure-detail");
    expect(detail).toHaveAttribute("data-code", "MEDIA_REJECTED");
    expect(detail).toHaveTextContent("Instagram görseli işleyemedi.");
    expect(detail).toHaveTextContent("Başka bir görsel seçip gönderiyi yeniden zamanlayın.");
    expect(within(detail).getByTestId("failure-final")).toHaveTextContent("Otomatik olarak tekrar denenmeyecek.");
    expect(screen.getByText("Başarısız")).toBeInTheDocument();
    await user.click(within(detail).getByRole("button", { name: "Düzenle ve yeniden gönder" }));
    expect(screen.getByLabelText("Başlık")).toHaveFocus();
  });

  it("a failure after retries ran out does not promise another try", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "failed", last_error_code: "PROVIDER_UNAVAILABLE" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const detail = await screen.findByTestId("failure-detail");
    expect(detail).toHaveTextContent("Birkaç denemeye rağmen yayınlanamadı.");
    expect(detail).not.toHaveTextContent("yeniden denenecek");
  });

  it("a retry says when it will be tried again", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            draftWithMedia({
              status: "retry_scheduled",
              scheduled_at: "2026-10-20T16:00:00Z",
              operation: {
                status: "retry_wait",
                attempts: 2,
                next_attempt_at: "2026-10-20T16:05:00Z",
                last_error_code: "PROVIDER_UNAVAILABLE",
              },
            }),
          ),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const detail = await screen.findByTestId("failure-detail");
    expect(detail).toHaveTextContent("Instagram'a şu anda ulaşılamıyor.");
    expect(within(detail).getByTestId("failure-retry")).toHaveTextContent("Tekrar denenecek: 19:05 (2. deneme yapıldı)");
    expect(within(detail).queryByRole("button", { name: "Düzenle ve yeniden gönder" })).toBeNull();
    expect(screen.getAllByText("Tekrar denenecek 19:05").length).toBeGreaterThan(0);
  });

  it("an attempt with an unknown outcome reads 'checking' and never offers to send again", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            draftWithMedia({
              status: "publishing",
              operation: { status: "outcome_unknown", attempts: 1, next_attempt_at: null, last_error_code: null },
            }),
          ),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const detail = await screen.findByTestId("failure-detail");
    expect(detail).toHaveAttribute("data-code", "OUTCOME_UNKNOWN");
    expect(detail).toHaveTextContent("Yayınlanıp yayınlanmadığını hâlâ kontrol ediyoruz.");
    expect(screen.getByText("Kontrol ediliyor")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Düzenle ve yeniden gönder" })).toBeNull();
    expect(screen.queryByText("Yayınlandı")).toBeNull();
  });

  it("a code the catalog does not know reads as a generic failure, never a bare code", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "failed", last_error_code: "SOMETHING_NEW" })) }));
    renderApp(ITEM_PAGE);
    const detail = await screen.findByTestId("failure-detail");
    expect(detail).toHaveTextContent("Yayınlanırken bir şeyler ters gitti.");
    expect(detail).not.toHaveTextContent("SOMETHING_NEW");
  });
});

describe("published post", () => {
  const published = (overrides: Partial<ContentItem> = {}) =>
    draftWithMedia({
      status: "published",
      published_at: "2026-10-20T16:00:00Z",
      external_media_id: "sim_1",
      external_permalink: "https://instagram.example/sim/sim_1",
      ...overrides,
    });

  it("links to the simulated post and carries the simulation badge", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(published()), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }));
    renderApp(ITEM_PAGE);
    const area = await screen.findByTestId("permalink");
    const link = within(area).getByRole("link", { name: "Gönderiyi aç" });
    expect(link).toHaveAttribute("href", "https://instagram.example/sim/sim_1");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(area).getByTestId("simulated-badge")).toBeInTheDocument();
    expect(screen.getByText("Yayınlandı")).toBeInTheDocument();
  });

  it("a real post has a link and no simulation badge", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(published({ is_simulated: false })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const area = await screen.findByTestId("permalink");
    expect(within(area).queryByTestId("simulated-badge")).toBeNull();
  });

  it("never turns a non-http permalink into a link", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(published({ external_permalink: "javascript:alert(1)" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    await screen.findByText("Yayınlandı");
    expect(screen.queryByTestId("permalink")).toBeNull();
  });

  it("a published post is read-only and cannot be cancelled", async () => {
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(published()), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }));
    renderApp(ITEM_PAGE);
    await screen.findByTestId("content-readonly");
    expect(screen.queryByRole("button", { name: "İptal et" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Zamanla" })).toBeNull();
  });
});

describe("approval and cancel", () => {
  it("staff do not see Cancel on drafts, scheduled or held items; owners and managers do", async () => {
    // The server decides (`can_cancel`); for staff it is false outside their own pending submission.
    for (const status of ["draft", "scheduled", "retry_scheduled", "on_hold"] as const) {
      mockApi(
        routes(
          {
            [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status, hold_reason: "FACT_CHANGED", can_cancel: false })),
            [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
          },
          "staff",
        ),
      );
      const { unmount } = renderApp(ITEM_PAGE);
      await screen.findByRole("heading", { level: 1 });
      expect(screen.queryByRole("button", { name: "İptal et" }), status).toBeNull();
      unmount();
      vi.unstubAllGlobals();
    }
    mockApi(routes({ [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "scheduled" })), [`GET ${BASE}/media/${MEDIA_ID}/content`]: image }, "manager"));
    renderApp(ITEM_PAGE);
    expect(await screen.findByRole("button", { name: "İptal et" })).toBeInTheDocument();
  });

  it("staff can withdraw their own pending submission, but not someone else's", async () => {
    mockApi(
      routes(
        {
          [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "pending_approval", can_cancel: true })),
          [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        },
        "staff",
      ),
    );
    const { unmount } = renderApp(ITEM_PAGE);
    expect(await screen.findByRole("button", { name: "İptal et" })).toBeInTheDocument();
    unmount();
    vi.unstubAllGlobals();

    mockApi(
      routes(
        {
          [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "pending_approval", can_cancel: false })),
          [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        },
        "staff",
      ),
    );
    renderApp(ITEM_PAGE);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: "İptal et" })).toBeNull();
  });

  it("a staff member withdraws their pending submission: asks once, then posts the cancel", async () => {
    let cancelled = false;
    const requests = mockApi(
      routes(
        {
          [`GET ${ITEM_URL}`]: () =>
            json(
              cancelled
                ? draftWithMedia({ status: "cancelled", can_cancel: false })
                : draftWithMedia({ status: "pending_approval", can_cancel: true }),
            ),
          [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
          [`POST ${ITEM_URL}/cancel`]: () => {
            cancelled = true;
            return json(draftWithMedia({ status: "cancelled", can_cancel: false }));
          },
        },
        "staff",
      ),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "İptal et" }));
    expect(posts(requests, `${ITEM_URL}/cancel`)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Evet, iptal et" }));
    expect(await screen.findByText("Bu içerik iptal edildi ve yayınlanmayacak.")).toBeInTheDocument();
    expect(posts(requests, `${ITEM_URL}/cancel`)).toHaveLength(1);
  });

  it("cancel asks once, then cancels, and the item reads İptal edildi", async () => {
    let cancelled = false;
    const requests = mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: cancelled ? "cancelled" : "scheduled" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        [`POST ${ITEM_URL}/cancel`]: () => {
          cancelled = true;
          return json(draftWithMedia({ status: "cancelled" }));
        },
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "İptal et" }));
    expect(posts(requests, `${ITEM_URL}/cancel`)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Evet, iptal et" }));
    expect(await screen.findByText("Bu içerik iptal edildi ve yayınlanmayacak.")).toBeInTheDocument();
    expect(screen.getByText("İptal edildi")).toBeInTheDocument();
    expect(posts(requests, `${ITEM_URL}/cancel`)).toHaveLength(1);
  });

  it("a cancel the server refuses (publishing) is explained, not hidden", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () => json(draftWithMedia({ status: "scheduled" })),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        [`POST ${ITEM_URL}/cancel`]: () => problem(409, "CONFLICT_STATE"),
      }),
    );
    renderApp(ITEM_PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "İptal et" }));
    await user.click(screen.getByRole("button", { name: "Evet, iptal et" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu işlem mevcut durumda yapılamaz.");
  });

  it("a staff submission waits for approval and says who must approve and by when", async () => {
    mockApi(
      routes(
        {
          [`GET ${ITEM_URL}`]: () =>
            json(
              draftWithMedia({
                status: "pending_approval",
                scheduled_at: "2026-10-21T16:00:00Z",
                approval: {
                  status: "pending",
                  subject_version: 1,
                  expires_at: "2026-10-21T16:00:00Z",
                  decided_by_name: null,
                  decided_at: null,
                  decision_note: null,
                  cancel_reason: null,
                },
              }),
            ),
          [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
        },
        "staff",
      ),
    );
    renderApp(ITEM_PAGE);
    const panel = await screen.findByTestId("status-panel");
    expect(panel).toHaveTextContent("sahip ya da yönetici onaylayınca zamanlanır");
    expect(panel).toHaveTextContent("19:00");
    expect(screen.getByText("Onay bekliyor")).toBeInTheDocument();
  });

  it("a rejected item shows who turned it down and the note", async () => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            draftWithMedia({
              status: "rejected",
              rejection_note: "Fiyatı kaldırın",
              approval: {
                status: "rejected",
                subject_version: 1,
                expires_at: "2026-10-21T16:00:00Z",
                decided_by_name: "Demo Sahip",
                decided_at: "2026-10-20T12:00:00Z",
                decision_note: "Fiyatı kaldırın",
                cancel_reason: null,
              },
            }),
          ),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    const panel = await screen.findByTestId("status-panel");
    expect(panel).toHaveTextContent("Demo Sahip reddetti.");
    expect(panel).toHaveTextContent("Not: Fiyatı kaldırın");
  });
});

describe("INV-18: every status on the detail page reads as the server state", () => {
  const ALL: ContentStatus[] = [
    "draft",
    "pending_approval",
    "scheduled",
    "publishing",
    "retry_scheduled",
    "on_hold",
    "published",
    "rejected",
    "failed",
    "cancelled",
  ];

  it.each(ALL)("%s", async (status) => {
    mockApi(
      routes({
        [`GET ${ITEM_URL}`]: () =>
          json(
            draftWithMedia({
              status,
              hold_reason: status === "on_hold" ? "FACT_CHANGED" : null,
              last_error_code: status === "failed" ? "MEDIA_REJECTED" : null,
              scheduled_at: "2026-10-21T16:00:00Z",
              published_at: status === "published" ? "2026-10-21T16:00:00Z" : null,
              external_permalink: status === "published" ? "https://instagram.example/sim/1" : null,
              operation:
                status === "retry_scheduled"
                  ? { status: "retry_wait", attempts: 1, next_attempt_at: "2026-10-21T16:05:00Z", last_error_code: "PROVIDER_UNAVAILABLE" }
                  : null,
            }),
          ),
        [`GET ${BASE}/media/${MEDIA_ID}/content`]: image,
      }),
    );
    renderApp(ITEM_PAGE);
    await screen.findByRole("heading", { level: 1 });
    const badges = document.querySelectorAll("[data-status]");
    const shown = [...badges].map((el) => el.getAttribute("data-status"));
    expect(shown.includes("published")).toBe(status === "published");
    // The word itself appears only for a published item (the page text around it says "Yayınlandığı zaman").
    expect(screen.queryAllByText("Yayınlandı").length > 0).toBe(status === "published");
    // Nothing on the page claims more than the state: a held, failed or scheduled item is never "sent".
    expect(screen.queryByText("Gönderildi")).toBeNull();
  });
});
