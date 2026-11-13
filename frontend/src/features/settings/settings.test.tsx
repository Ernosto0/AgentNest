import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CalendarConnection, SocialAccount, Workspace } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) => (m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m)),
};

const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
const PAGE = `/w/${WS_GOLKENT}/more/settings`;

const ACTIVE = {
  workspace_id: WS_GOLKENT,
  status: "active",
  is_deleting: false,
  deletion_requested_at: null,
  deletion_scheduled_at: null,
  days_remaining: null,
  can_cancel: false,
};
const DELETING = {
  workspace_id: WS_GOLKENT,
  status: "deleting",
  is_deleting: true,
  deletion_requested_at: "2026-11-03T09:00:00Z",
  deletion_scheduled_at: "2026-11-10T09:00:00Z",
  days_remaining: 6,
  can_cancel: true,
};

function instagram(overrides: Partial<SocialAccount> = {}): SocialAccount {
  return {
    id: "acc-1",
    platform: "instagram",
    provider_kind: "mock",
    username: "golkent.demo",
    status: "connected",
    capabilities: {},
    connection_expires_at: null,
    last_error_code: null,
    degraded_until: null,
    is_simulated: true,
    ...overrides,
  };
}

function calendar(overrides: Partial<CalendarConnection> = {}): CalendarConnection {
  return {
    id: "cal-1",
    provider_kind: "google",
    external_account_id: "ext",
    account_email: "studio@example.com",
    calendar_id: "primary",
    calendar_summary: "Studio",
    calendar_timezone: "Europe/Istanbul",
    status: "needs_reauth",
    capabilities: {},
    default_slot_duration_minutes: 60,
    last_error_code: null,
    is_simulated: false,
    connected_at: "2026-11-01T10:00:00Z",
    disconnected_at: null,
    created_at: "2026-11-01T10:00:00Z",
    ...overrides,
  } as CalendarConnection;
}

function routes(
  extra: Record<string, (request: RecordedRequest) => Response> = {},
  options: { me?: typeof ME; ws?: Partial<Workspace> } = {},
) {
  return {
    "GET /api/v1/meta": () =>
      json({
        product_name: "AgentNest",
        demo_tools_enabled: true,
        llm_mode: "fake",
        supported_locales: ["tr", "en"],
        instagram_providers: ["mock"],
        mock_requires_demo_workspace: false,
      }),
    "GET /api/v1/auth/me": () => json(options.me ?? ME),
    "GET /api/v1/auth/sessions": () =>
      json([
        {
          id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
          created_at: "2026-10-30T10:00:00Z",
          last_seen_at: "2026-10-30T10:00:00Z",
          expires_at: "2026-11-13T10:00:00Z",
          user_agent: "Mozilla/5.0",
          ip_address: "127.0.0.1",
          is_current: true,
        },
      ]),
    [`GET ${BASE}`]: () => json(workspace(WS_GOLKENT, options.ws)),
    [`GET ${BASE}/readiness`]: () => json(READINESS),
    [`GET ${BASE}/members`]: () =>
      json({
        items: [
          { user_id: ME.user.id, email: ME.user.email, display_name: ME.user.display_name, role: "owner", joined_at: "2026-10-15T12:00:00Z" },
          { user_id: "u2", email: "staff@demo.local", display_name: "Personel", role: "staff", joined_at: "2026-10-16T12:00:00Z" },
        ],
      }),
    [`GET ${BASE}/deletion-status`]: () => json(ACTIVE),
    ...extra,
  };
}

describe("SettingsPage", () => {
  it("groups settings into navigable sections with readable workspace details for the owner", async () => {
    mockApi(
      routes({
        [`GET ${BASE}/social-accounts`]: () => json({ items: [instagram()], next_cursor: null }),
        [`GET ${BASE}/calendar`]: () => json({ items: [calendar()] }),
      }),
    );
    renderApp(PAGE);

    const main = within(await screen.findByRole("main"));
    expect(main.getByRole("heading", { name: "Ayarlar", level: 1 })).toBeInTheDocument();

    const nav = within(main.getByRole("navigation", { name: "Ayar bölümleri" }));
    for (const [name, hash] of [["Hesap", "#account"], ["Çalışma alanı", "#workspace"], ["Güvenlik", "#security"], ["Bağlantılar", "#connections"], ["Gizlilik ve veriler", "#privacy"]]) {
      expect(nav.getByRole("link", { name })).toHaveAttribute("href", hash);
    }

    // Account identity and role
    expect(main.getAllByText("Demo Sahip").length).toBeGreaterThanOrEqual(1);
    expect(main.getByText("owner@demo.local")).toBeInTheDocument();
    expect(main.getByText("Sahip")).toBeInTheDocument();

    // Friendly workspace details, not raw identifiers
    const details = within(main.getByRole("region", { name: "Çalışma alanı bilgileri" }));
    expect(details.getByText("Gölkent Fitness")).toBeInTheDocument();
    expect(details.getByText("Türkiye")).toBeInTheDocument();
    expect(details.getByText(/\(TRY\)$/)).toBeInTheDocument();
    expect(details.getByText(/^Istanbul \(GMT\+03:00\)$/)).toBeInTheDocument();
    expect(details.getByText("Türkçe")).toBeInTheDocument();
    expect(details.queryByText("Europe/Istanbul")).toBeNull();
    expect(details.getByRole("button", { name: /Düzenle/ })).toBeInTheDocument();

    // Administration links keep their routes; the member count comes from the API
    expect(main.getByRole("link", { name: /Ekip üyeleri/ })).toHaveAttribute("href", `${PAGE}/members`);
    expect(await main.findByText("2 üye")).toBeInTheDocument();
    expect(main.getByRole("link", { name: /Sistem durumu/ })).toHaveAttribute("href", `${PAGE}/system-health`);

    // Connection states come from the backend, with the simulation badge and the next action
    expect(await main.findByText("@golkent.demo")).toBeInTheDocument();
    expect(main.getByText("SİMÜLASYON")).toBeInTheDocument();
    expect(main.getByRole("link", { name: "Instagram: Yönet" })).toHaveAttribute("href", `${PAGE}/connections`);
    expect(await main.findByText("Yeniden bağlanmalı")).toBeInTheDocument();
    expect(main.getByRole("link", { name: "Google Calendar: Yeniden bağla" })).toHaveAttribute("href", `${PAGE}/connections#calendar`);

    // Privacy points at the real data-rights locations
    expect(main.getByRole("link", { name: "Gelen Kutusu'nu aç" })).toHaveAttribute("href", `/w/${WS_GOLKENT}/inbox`);
    expect(main.getByRole("link", { name: /Politikayı oku/ })).toHaveAttribute("href", "/privacy");

    // Owner-only deletion
    expect(await main.findByRole("button", { name: "Çalışma alanını sil…" })).toBeInTheDocument();
  });

  it("keeps staff read-only: no edits, no system health, no deletion, view-only connections", async () => {
    const requests = mockApi(routes({}, { me: STAFF_ME }));
    renderApp(PAGE);

    const main = within(await screen.findByRole("main"));
    expect(await main.findByText("Personel", { selector: "span" })).toBeInTheDocument();
    expect(main.getByText("Çalışma alanı bilgilerini yalnızca sahip değiştirebilir.")).toBeInTheDocument();
    expect(main.queryByRole("button", { name: /^Düzenle$/ })).toBeNull();
    expect(main.queryByRole("link", { name: /Sistem durumu/ })).toBeNull();
    expect(main.getByRole("link", { name: /Ekip üyeleri/ })).toBeInTheDocument();
    expect(await main.findByRole("link", { name: "Instagram: Görüntüle" })).toBeInTheDocument();
    expect(main.queryByRole("button", { name: "Çalışma alanını sil…" })).toBeNull();
    expect(main.getByText(/Sahip, bir müşterinin konuşmasını/)).toBeInTheDocument();
    // Staff never ask for the owner-only deletion status
    expect(requests.some((r) => r.path.endsWith("/deletion-status"))).toBe(false);
  });

  it("switches the interface language and saves it to the account", async () => {
    const requests = mockApi(
      routes({
        "PATCH /api/v1/auth/me": (req) => {
          const body = (req.body ?? {}) as { ui_locale?: "tr" | "en" };
          return json({ ...ME, user: { ...ME.user, ui_locale: body.ui_locale ?? "en" } });
        },
      }),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    const english = await screen.findByRole("radio", { name: "English" });
    expect(screen.getByRole("radio", { name: "Türkçe" })).toBeChecked();
    await user.click(english);

    await waitFor(() => expect(requests.some((r) => r.path === "/api/v1/auth/me" && r.method === "PATCH")).toBe(true));
    expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ ui_locale: "en" });
    expect(await screen.findByRole("heading", { name: "Settings", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Saved to your account.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "English" })).toBeChecked();
  });

  it("edits the display name through the account endpoint", async () => {
    const requests = mockApi(
      routes({
        "PATCH /api/v1/auth/me": (req) => {
          const body = req.body as { display_name: string };
          return json({ ...ME, user: { ...ME.user, display_name: body.display_name } });
        },
      }),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Görünen adı düzenle" }));
    const field = screen.getByLabelText("Görünen ad");
    await user.clear(field);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(screen.getByText("Bir ad girin.")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "PATCH")).toBe(false);

    await user.type(field, "  Ayşe Yılmaz ");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ display_name: "Ayşe Yılmaz" }));
    expect(await screen.findByText("Ad kaydedildi.")).toBeInTheDocument();
  });

  it("lets the owner rename the workspace and change its time zone with a visible consequence", async () => {
    let current = workspace(WS_GOLKENT);
    const requests = mockApi(
      routes({
        [`GET ${BASE}`]: () => json(current),
        [`PATCH ${BASE}`]: (req) => {
          current = { ...current, ...(req.body as Partial<Workspace>) };
          return json(current);
        },
      }),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    const details = within(await screen.findByRole("region", { name: "Çalışma alanı bilgileri" }));
    await user.click(details.getByRole("button", { name: /Düzenle/ }));
    const name = details.getByLabelText("Çalışma alanı adı");
    await user.clear(name);
    await user.type(name, "Gölkent Fitness & Spa");
    await user.selectOptions(details.getByLabelText("Zaman dilimi"), "Europe/Berlin");
    expect(details.getByText("Saatler yeni zaman dilimine göre işleyecek")).toBeInTheDocument();
    await user.click(details.getByRole("button", { name: "Değişiklikleri kaydet" }));

    await waitFor(() =>
      expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ name: "Gölkent Fitness & Spa", timezone: "Europe/Berlin" }),
    );
    expect(await details.findByText("Çalışma alanı bilgileri kaydedildi.")).toBeInTheDocument();
    expect(details.getByText("Gölkent Fitness & Spa")).toBeInTheDocument();
    expect(details.getByText(/^Berlin \(GMT/)).toBeInTheDocument();
  });

  it("shows a server rejection of the workspace edit without losing the input", async () => {
    mockApi(routes({ [`PATCH ${BASE}`]: () => problem(403, "FORBIDDEN") }));
    renderApp(PAGE);
    const user = userEvent.setup();

    const details = within(await screen.findByRole("region", { name: "Çalışma alanı bilgileri" }));
    await user.click(details.getByRole("button", { name: /Düzenle/ }));
    const name = details.getByLabelText("Çalışma alanı adı");
    await user.type(name, " 2");
    await user.click(details.getByRole("button", { name: "Değişiklikleri kaydet" }));
    expect(await details.findByText("Rolünüz bu işlem için yetkili değil.")).toBeInTheDocument();
    expect(name).toHaveValue("Gölkent Fitness 2");
  });

  it("signs out and redirects to login", async () => {
    let loggedOut = false;
    mockApi(
      routes({
        "POST /api/v1/auth/logout": () => {
          loggedOut = true;
          return noContent();
        },
      }),
    );
    const { router } = renderApp(PAGE);

    await userEvent.setup().click(await screen.findByRole("button", { name: "Oturumu kapat" }));
    await waitFor(() => expect(loggedOut).toBe(true));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });
});

describe("Workspace deletion", () => {
  it("requires the exact workspace name, and cancelling the dialog sends nothing", async () => {
    let deleting = false;
    const requests = mockApi(
      routes({
        [`GET ${BASE}/deletion-status`]: () => json(deleting ? DELETING : ACTIVE),
        [`POST ${BASE}/delete-request`]: () => {
          deleting = true;
          return json(DELETING);
        },
      }),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Çalışma alanını sil…" }));
    let dialog = within(await screen.findByRole("dialog", { name: "Gölkent Fitness silinsin mi?" }));
    expect(dialog.getByText(/İptal etmek Instagram'ı yeniden bağlamaz/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(requests.some((r) => r.path.endsWith("/delete-request"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "Çalışma alanını sil…" }));
    dialog = within(await screen.findByRole("dialog"));
    const confirm = dialog.getByRole("button", { name: "Çalışma alanını sil" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText(/Onaylamak için çalışma alanı adını yazın/), "gölkent fitness");
    expect(confirm).toBeDisabled(); // case matters: deliberate, exact confirmation
    await user.clear(dialog.getByLabelText(/Onaylamak için/));
    await user.type(dialog.getByLabelText(/Onaylamak için/), "Gölkent Fitness");
    await user.click(confirm);

    await waitFor(() => expect(requests.some((r) => r.method === "POST" && r.path.endsWith("/delete-request"))).toBe(true));
    expect(await screen.findByRole("heading", { name: "Silme planlandı" })).toBeInTheDocument();
    expect(screen.getByText("İptal için 6 gün kaldı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Silme talebini iptal et" })).toBeInTheDocument();
  });

  it("keeps the dialog open with the error when the request fails", async () => {
    mockApi(routes({ [`POST ${BASE}/delete-request`]: () => problem(500, "INTERNAL_ERROR") }));
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Çalışma alanını sil…" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Onaylamak için/), "Gölkent Fitness");
    await user.click(dialog.getByRole("button", { name: "Çalışma alanını sil" }));
    expect(await dialog.findByText("Bir şeyler ters gitti.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("cancels a scheduled deletion and says what is not restored", async () => {
    let deleting = true;
    const requests = mockApi(
      routes(
        {
          [`GET ${BASE}/deletion-status`]: () => json(deleting ? DELETING : ACTIVE),
          [`POST ${BASE}/cancel-deletion`]: () => {
            deleting = false;
            return json(ACTIVE);
          },
        },
        { ws: { status: "deleting" } },
      ),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    expect(await screen.findByText("Bu çalışma alanı silinmek üzere planlandı")).toBeInTheDocument();
    expect(await screen.findByText(/kalıcı silme için planlandı/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Silme talebini iptal et" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/cancel-deletion"))).toBe(true));
    expect(await screen.findByText("Silme talebi iptal edildi")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bağlantılara git" })).toHaveAttribute("href", `${PAGE}/connections`);
  });

  it("tells non-owners about a scheduled deletion without offering controls", async () => {
    mockApi(routes({}, { me: STAFF_ME, ws: { status: "deleting" } }));
    renderApp(PAGE);
    expect(await screen.findByText("Otomasyon durduruldu. Silme talebini yalnızca sahip iptal edebilir.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Silme talebini iptal et" })).toBeNull();
  });

  it("shows the end of the cancellation window instead of a cancel button", async () => {
    mockApi(routes({ [`GET ${BASE}/deletion-status`]: () => json({ ...DELETING, days_remaining: 0, can_cancel: false }) }, { ws: { status: "deleting" } }));
    renderApp(PAGE);
    expect(await screen.findByText("İptal süresi sona erdi.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Silme talebini iptal et" })).toBeNull();
  });
});
