import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ContentItem, ContentTab } from "@/api/types";
import { contentItem, socialAccount } from "@/test/contentFixtures";
import { ME, READINESS, WS_GOLKENT, fact, workspace } from "@/test/fixtures";
import { json, mockApi, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { todayIn } from "@/features/reports/dates";

afterEach(() => vi.unstubAllGlobals());

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const LIST_URL = `${BASE}/content-items`;

type Handlers = Record<string, (request: RecordedRequest) => Response>;

function routes(byTab: Partial<Record<ContentTab, ContentItem[]>>, extra: Handlers = {}): Handlers {
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/facts`]: () => json({ items: [fact()] }),
    [`GET ${BASE}/social-accounts`]: () => json({ items: [socialAccount()], next_cursor: null }),
    [`GET ${LIST_URL}`]: (request) => {
      const tab = new URLSearchParams(request.search).get("tab") as ContentTab;
      return json({ items: byTab[tab] ?? [], next_cursor: null });
    },
    ...extra,
  };
}

const many = (n: number, overrides: Partial<ContentItem> = {}) =>
  Array.from({ length: n }, (_, i) => contentItem({ id: `p${i}`, title: `Gönderi ${i}`, status: "published", ...overrides }));

describe("content library status tiles", () => {
  it("counts every tab from its own list, says when a list is full, and keeps the tab's name as its name", async () => {
    const requests = mockApi(
      routes({
        drafts: [
          contentItem({ id: "d1", title: "Taslak A" }),
          contentItem({ id: "d2", title: "Taslak B", status: "pending_approval" }),
        ],
        published: many(50),
        problems: [contentItem({ id: "x", title: "Sorun", status: "failed" })],
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);

    const drafts = await screen.findByRole("tab", { name: "Taslaklar" });
    await waitFor(() => expect(within(drafts).getByText("2")).toBeInTheDocument());
    expect(within(drafts).getByText("Onay bekleyen: 1")).toBeInTheDocument();
    expect(drafts).toHaveAccessibleDescription(/2.*Onay bekleyen: 1/);

    const published = screen.getByRole("tab", { name: "Yayınlanan" });
    await waitFor(() => expect(within(published).getByText("50+")).toBeInTheDocument());
    expect(within(screen.getByRole("tab", { name: "Zamanlanan" })).getByText("0")).toBeInTheDocument();
    expect(within(screen.getByRole("tab", { name: "Sorunlar" })).getByText("İlgilenmeniz gerekiyor")).toBeInTheDocument();

    // Each list asks for an explicit page size.
    const limits = requests.filter((r) => r.path === LIST_URL).map((r) => new URLSearchParams(r.search).get("limit"));
    expect(new Set(limits)).toEqual(new Set(["50"]));
  });

  it("moves between tabs with the arrow keys", async () => {
    mockApi(routes({ drafts: [contentItem({ title: "Taslak A" })], scheduled: [] }));
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    const drafts = await screen.findByRole("tab", { name: "Taslaklar" });
    drafts.focus();
    await user.keyboard("{ArrowRight}");
    const scheduled = screen.getByRole("tab", { name: "Zamanlanan" });
    expect(scheduled).toHaveAttribute("aria-selected", "true");
    expect(scheduled).toHaveFocus();
  });

  it("explains a problem on its card", async () => {
    mockApi(routes({ problems: [contentItem({ title: "Fiyat gönderisi", status: "on_hold", hold_reason: "FACT_CHANGED" })] }));
    renderApp(`/w/${WS_GOLKENT}/content?tab=problems`);
    const card = await screen.findByTestId("content-card");
    expect(within(card).getByText("Beklemede")).toBeInTheDocument();
    expect(within(card).getByText(/işletme bilgisi değiştiği için/)).toBeInTheDocument();
  });

  it("marks a draft the assistant prepared", async () => {
    mockApi(routes({ drafts: [contentItem({ generation: { status: "succeeded", error_code: null } })] }));
    renderApp(`/w/${WS_GOLKENT}/content`);
    const card = await screen.findByTestId("content-card");
    expect(within(card).getByText("YZ")).toHaveAttribute("title", "Asistan hazırladı");
  });
});

describe("content library empty states", () => {
  it("gives an empty account a short path from idea to Instagram, leading to the composer", async () => {
    mockApi(routes({}));
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    expect(await screen.findByText("İçerik kütüphaneniz henüz boş")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Asistanla başlayın" }));
    expect(screen.getByLabelText("Asistan ne hazırlasın?")).toHaveFocus();
  });

  it("an empty Scheduled tab points to the drafts that exist", async () => {
    mockApi(routes({ drafts: [contentItem({ title: "Hazır taslak" })] }));
    renderApp(`/w/${WS_GOLKENT}/content?tab=scheduled`);
    const user = userEvent.setup();
    expect(await screen.findByText("Zamanlanmış içerik yok")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Taslaklara bakın" }));
    expect(screen.getByRole("tab", { name: "Taslaklar" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Hazır taslak")).toBeInTheDocument();
  });

  it("an empty Problems tab reads as all clear", async () => {
    mockApi(routes({ drafts: [contentItem()] }));
    renderApp(`/w/${WS_GOLKENT}/content?tab=problems`);
    expect(await screen.findByText("Beklemede, başarısız ya da reddedilmiş içerik yok.")).toBeInTheDocument();
  });
});

describe("content library filters", () => {
  it("searches titles and text and filters by format over the listed items", async () => {
    mockApi(
      routes({
        drafts: [
          contentItem({ id: "a", title: "Pilates duyurusu", caption: "Sabah grubu" }),
          contentItem({ id: "b", title: "Deneme dersi", content_type: "story_image", overlay_text_suggestions: ["Ücretsiz deneme"] }),
          contentItem({ id: "c", title: "Kampanya", caption: "İndirimli üyelik" }),
        ],
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    const titles = () => screen.queryAllByTestId("content-card-title").map((node) => node.textContent);
    await screen.findByText("Pilates duyurusu");

    await user.click(screen.getByRole("button", { name: "Story'ler" }));
    expect(titles()).toEqual(["Deneme dersi"]);
    await user.click(screen.getByRole("button", { name: "Tümü" }));

    await user.type(screen.getByLabelText("İçerikte ara"), "İNDİRİM");
    expect(titles()).toEqual(["Kampanya"]);
    expect(screen.getByText("3 içerikten 1 tanesi gösteriliyor")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("İçerikte ara"));
    await user.type(screen.getByLabelText("İçerikte ara"), "yok böyle");
    expect(screen.getByTestId("content-filter-empty")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filtreleri temizle" }));
    expect(titles()).toHaveLength(3);
  });
});

describe("content composer", () => {
  it("opens the draft sheet with the brief and format filled in, and generates nothing until it is sent", async () => {
    const requests = mockApi(routes({}));
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();

    const composer = await screen.findByTestId("content-composer");
    expect(await within(composer).findByText("Yayın hesabı: @golkent.fitness")).toBeInTheDocument();
    await user.type(within(composer).getByLabelText("Asistan ne hazırlasın?"), "Cumartesi deneme dersi");
    await user.click(within(composer).getByLabelText("Story"));
    await user.click(within(composer).getByRole("button", { name: "Taslak iste" }));

    const dialog = await screen.findByRole("dialog", { name: "Yeni içerik" });
    expect(within(dialog).getByLabelText("Ne paylaşmak istiyorsunuz?")).toHaveValue("Cumartesi deneme dersi");
    expect(within(dialog).getByLabelText("Story")).toBeChecked();
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("starts a blank draft of the chosen format", async () => {
    mockApi(routes({}));
    renderApp(`/w/${WS_GOLKENT}/content`);
    const user = userEvent.setup();
    const composer = await screen.findByTestId("content-composer");
    await user.click(within(composer).getByLabelText("Story"));
    await user.click(within(composer).getByRole("button", { name: "Boş taslak" }));
    const dialog = await screen.findByRole("dialog", { name: "Yeni içerik" });
    expect(within(dialog).getByRole("tab", { name: "Boş taslak" })).toHaveAttribute("aria-selected", "true");
    expect(within(dialog).getByLabelText("Story")).toBeChecked();
  });
});

describe("content agenda", () => {
  const soon = () => new Date(Date.now() + 60_000).toISOString();

  it("puts a scheduled item on its day of the current week and offers the full list", async () => {
    const at = soon();
    mockApi(routes({ scheduled: [contentItem({ id: "s1", title: "Akşam dersi", status: "scheduled", scheduled_at: at })] }));
    renderApp(`/w/${WS_GOLKENT}/content?view=agenda`);
    const user = userEvent.setup();

    const day = await screen.findByTestId(`agenda-day-${todayIn("Europe/Istanbul", new Date(at))}`);
    expect(await within(day).findByText("Akşam dersi")).toBeInTheDocument();
    expect(day).toHaveAttribute("aria-current", "date");
    expect(screen.getByTestId("agenda-prev")).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Liste" }));
    const list = await screen.findByTestId("agenda-list");
    expect(within(list).getByText("Akşam dersi")).toBeInTheDocument();
    expect(within(list).getByText("Zamanlandı")).toBeInTheDocument();
  });

  it("moves between weeks and back to this one", async () => {
    mockApi(routes({ scheduled: [] }));
    renderApp(`/w/${WS_GOLKENT}/content?view=agenda`);
    const user = userEvent.setup();
    const heading = await screen.findByRole("heading", { level: 2, name: /\d{4}/ });
    const thisWeek = heading.textContent;
    await user.click(screen.getByTestId("agenda-next"));
    await waitFor(() => expect(heading.textContent).not.toBe(thisWeek));
    await user.click(screen.getByRole("button", { name: "Bu hafta" }));
    await waitFor(() => expect(heading.textContent).toBe(thisWeek));
  });

  it("says when nothing is scheduled and points to the drafts that exist", async () => {
    mockApi(routes({ drafts: [contentItem(), contentItem({ id: "d2" })], scheduled: [] }));
    renderApp(`/w/${WS_GOLKENT}/content?view=agenda`);
    expect(await screen.findByText("Henüz zamanlanmış içerik yok.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Taslaklara bakın (2)" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/content?tab=drafts`,
    );
  });

  it("does not show days after a full page as free", async () => {
    // 50 items, all within the next minute: every later day is unknown.
    const at = soon();
    mockApi(routes({ scheduled: many(50, { status: "scheduled", scheduled_at: at }) }));
    renderApp(`/w/${WS_GOLKENT}/content?view=agenda`);
    expect(await screen.findByText(/Yalnızca ilk 50 zamanlanmış içerik yüklendi/)).toBeInTheDocument();
    const today = todayIn("Europe/Istanbul", new Date(at));
    const days = screen.getAllByTestId(/^agenda-day-/);
    const later = days.filter((node) => (node.getAttribute("data-testid") ?? "").slice(-10) > today);
    for (const node of later) expect(within(node).getByText("Yüklenmedi")).toBeInTheDocument();
  });
});
