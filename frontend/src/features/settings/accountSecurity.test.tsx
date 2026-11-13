import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const CHROME_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
const SAFARI_IPHONE =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

const CURRENT = "3fa85f64-5717-4562-b3fc-2c963f66afa6";
const PHONE = "7ca49e12-3214-4a62-93cb-5b123f66bbb2";
const UNKNOWN = "9d1f0c33-8f61-4c39-9a0e-0b5e4d3c2a11";

const SESSIONS = [
  {
    id: PHONE,
    created_at: "2026-10-29T08:00:00Z",
    last_seen_at: "2026-10-29T12:00:00Z",
    expires_at: "2026-11-12T08:00:00Z",
    user_agent: SAFARI_IPHONE,
    ip_address: "203.0.113.44",
    is_current: false,
  },
  {
    id: CURRENT,
    created_at: "2026-10-30T10:00:00Z",
    last_seen_at: "2026-10-30T10:00:00Z",
    expires_at: "2026-11-13T10:00:00Z",
    user_agent: CHROME_WINDOWS,
    ip_address: "198.51.100.1",
    is_current: true,
  },
  {
    id: UNKNOWN,
    created_at: "2026-10-20T08:00:00Z",
    last_seen_at: "2026-10-21T08:00:00Z",
    expires_at: "2026-11-04T08:00:00Z",
    user_agent: "python-requests/2.32",
    ip_address: null,
    is_current: false,
  },
];

function routes(extra: Record<string, (request: RecordedRequest) => Response> = {}) {
  const base = `/api/v1/workspaces/${WS_GOLKENT}`;
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
    "GET /api/v1/auth/me": () => json(ME),
    "GET /api/v1/auth/sessions": () => json(SESSIONS),
    [`GET ${base}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/members`]: () => json({ items: [] }),
    [`GET ${base}/deletion-status`]: () =>
      json({ workspace_id: WS_GOLKENT, status: "active", is_deleting: false, deletion_requested_at: null, deletion_scheduled_at: null, days_remaining: null, can_cancel: false }),
    ...extra,
  };
}

async function sessionsPanel() {
  return within(await screen.findByRole("region", { name: "Oturum açık cihazlar" }));
}

describe("Signed-in devices", () => {
  it("names devices in words, puts this device first and never shows raw user agents", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const panel = await sessionsPanel();
    const rows = await panel.findAllByTestId("session-row");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("Chrome · Windows")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Bu cihaz")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Şu anda etkin")).toBeInTheDocument();
    expect(within(rows[0]!).queryByRole("button")).toBeNull(); // sign out of this device is the account action
    expect(within(rows[1]!).getByText("Safari · iOS")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Telefon")).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/IP 203\.0\.113\.44/)).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Bilinmeyen tarayıcı")).toBeInTheDocument();
    expect(panel.queryByText(/Mozilla|python-requests/)).toBeNull();
  });

  it("confirms before signing out one device, and cancelling sends nothing", async () => {
    const user = userEvent.setup();
    let sessions = SESSIONS;
    const requests = mockApi(
      routes({
        "GET /api/v1/auth/sessions": () => json(sessions),
        [`DELETE /api/v1/auth/sessions/${PHONE}`]: () => {
          sessions = sessions.filter((s) => s.id !== PHONE);
          return noContent();
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/settings`);
    const panel = await sessionsPanel();

    await user.click(await panel.findByRole("button", { name: "Safari · iOS oturumunu kapat" }));
    let dialog = within(await screen.findByRole("dialog", { name: "Safari · iOS oturumu kapatılsın mı?" }));
    await user.click(dialog.getByRole("button", { name: "Vazgeç" }));
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);

    await user.click(panel.getByRole("button", { name: "Safari · iOS oturumunu kapat" }));
    dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Oturumu kapat" }));

    await waitFor(() => expect(requests.some((r) => r.method === "DELETE" && r.path === `/api/v1/auth/sessions/${PHONE}`)).toBe(true));
    expect(await panel.findByText("Safari · iOS oturumu kapatıldı.")).toBeInTheDocument();
    await waitFor(() => expect(panel.queryByText("Safari · iOS")).toBeNull());
  });

  it("signs out all other devices after confirmation and keeps this one", async () => {
    const user = userEvent.setup();
    let sessions = SESSIONS;
    const requests = mockApi(
      routes({
        "GET /api/v1/auth/sessions": () => json(sessions),
        "POST /api/v1/auth/sessions/revoke-all": () => {
          sessions = sessions.filter((s) => s.is_current);
          return noContent();
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/settings`);
    const panel = await sessionsPanel();

    await user.click(await panel.findByRole("button", { name: "Diğer cihazlardan çıkış yap" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Diğer tüm cihazlardan çıkış yapılsın mı?" }));
    expect(dialog.getByText(/Diğer 2 cihazda/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Diğer cihazlardan çıkış yap" }));

    await waitFor(() => expect(requests.find((r) => r.path === "/api/v1/auth/sessions/revoke-all")?.body).toEqual({ include_current: false }));
    expect(await panel.findByText("Diğer tüm cihazlardaki oturumlar kapatıldı.")).toBeInTheDocument();
    expect(await panel.findByText("Başka cihazda açık oturum yok.")).toBeInTheDocument();
    expect(panel.getAllByTestId("session-row")).toHaveLength(1);
  });

  it("shows a failed revocation and keeps the device listed", async () => {
    const user = userEvent.setup();
    mockApi(routes({ [`DELETE /api/v1/auth/sessions/${PHONE}`]: () => problem(500, "INTERNAL_ERROR") }));
    renderApp(`/w/${WS_GOLKENT}/more/settings`);
    const panel = await sessionsPanel();

    await user.click(await panel.findByRole("button", { name: "Safari · iOS oturumunu kapat" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Oturumu kapat" }));
    expect(await panel.findByText("Bir şeyler ters gitti.")).toBeInTheDocument();
    expect(panel.getByText("Safari · iOS")).toBeInTheDocument();
  });
});

describe("Password change", () => {
  async function fill(current: string, next: string, confirm = next) {
    const user = userEvent.setup();
    const form = within(await screen.findByRole("region", { name: "Şifre" }));
    await user.type(form.getByLabelText("Mevcut şifre"), current);
    await user.type(form.getByLabelText("Yeni şifre"), next);
    await user.type(form.getByLabelText("Yeni şifreyi onayla"), confirm);
    await user.click(form.getByRole("button", { name: "Şifreyi güncelle" }));
    return form;
  }

  it("updates the password and says other devices were signed out", async () => {
    const requests = mockApi(routes({ "POST /api/v1/auth/password": () => noContent() }));
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const form = await fill("correct-horse-battery", "a-new-strong-password-2026");
    await waitFor(() =>
      expect(requests.find((r) => r.path === "/api/v1/auth/password")?.body).toEqual({
        current_password: "correct-horse-battery",
        new_password: "a-new-strong-password-2026",
      }),
    );
    expect(await form.findByText("Şifre güncellendi.")).toBeInTheDocument();
    expect(form.getByText(/Diğer cihazlarınızdaki oturumlar kapatıldı/)).toBeInTheDocument();
    expect(form.getByLabelText("Mevcut şifre")).toHaveValue("");
  });

  it("checks length and confirmation before sending anything", async () => {
    const requests = mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const form = await fill("correct-horse-battery", "short", "shorter");
    expect(form.getByText("En az 12 karakter kullanın.")).toBeInTheDocument();
    expect(form.getByText("Yeni şifreler eşleşmiyor.")).toBeInTheDocument();
    expect(form.getByLabelText("Yeni şifre")).toHaveAttribute("aria-invalid", "true");
    expect(requests.some((r) => r.path === "/api/v1/auth/password")).toBe(false);
  });

  it("puts a wrong current password on its field without signing the user out", async () => {
    mockApi(routes({ "POST /api/v1/auth/password": () => problem(401, "INVALID_CREDENTIALS") }));
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const form = await fill("wrong-password-1", "a-new-strong-password-2026");
    expect(await form.findByText("Mevcut şifre doğru değil.")).toBeInTheDocument();
    expect(form.getByLabelText("Mevcut şifre")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("heading", { name: "Ayarlar", level: 1 })).toBeInTheDocument();
  });

  it("maps the server's common-password rule to the new password field", async () => {
    mockApi(
      routes({
        "POST /api/v1/auth/password": () =>
          problem(422, "VALIDATION_FAILED", { errors: [{ field: "new_password", code: "too_common", params: {} }] }),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const form = await fill("correct-horse-battery", "password1234");
    expect(await form.findByText(/Bu şifre çok yaygın/)).toBeInTheDocument();
  });

  it("reveals and hides a password with a labelled toggle", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/settings`);
    const user = userEvent.setup();

    const form = within(await screen.findByRole("region", { name: "Şifre" }));
    const field = form.getByLabelText("Mevcut şifre");
    expect(field).toHaveAttribute("type", "password");
    const [toggle] = form.getAllByRole("button", { name: "Şifreyi göster" });
    await user.click(toggle!);
    expect(field).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveAccessibleName("Şifreyi gizle");
  });
});
