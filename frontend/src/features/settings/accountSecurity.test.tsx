import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const MOCK_SESSIONS = [
  {
    id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    created_at: "2026-10-30T10:00:00Z",
    last_seen_at: "2026-10-30T10:00:00Z",
    expires_at: "2026-11-13T10:00:00Z",
    user_agent: "Mozilla/5.0 Chrome/130",
    ip_address: "198.51.100.1",
    is_current: true,
  },
  {
    id: "7ca49e12-3214-4a62-93cb-5b123f66bbb2",
    created_at: "2026-10-29T08:00:00Z",
    last_seen_at: "2026-10-29T12:00:00Z",
    expires_at: "2026-11-12T08:00:00Z",
    user_agent: "Safari/18.0 macOS",
    ip_address: "203.0.113.44",
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
    "GET /api/v1/auth/sessions": () => json(MOCK_SESSIONS),
    [`GET ${base}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

describe("AccountSecurity", () => {
  it("displays sessions and allows revoking another session", async () => {
    const user = userEvent.setup();
    const requests = mockApi(
      routes({
        "DELETE /api/v1/auth/sessions/7ca49e12-3214-4a62-93cb-5b123f66bbb2": () => noContent(),
      })
    );

    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    expect(await screen.findByText("Aktif oturumlar")).toBeInTheDocument();
    expect(await screen.findByText("Bu cihaz")).toBeInTheDocument();
    expect(screen.getByText("Safari/18.0 macOS")).toBeInTheDocument();

    const revokeButtons = screen.getAllByRole("button", { name: "Oturumu kapat" });
    // Click revoke on the other session
    await user.click(revokeButtons[revokeButtons.length - 1]!);

    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.path ===
              "/api/v1/auth/sessions/7ca49e12-3214-4a62-93cb-5b123f66bbb2" &&
            r.method === "DELETE"
        )
      ).toBe(true)
    );
  });

  it("submits password change with minimum length validation", async () => {
    const user = userEvent.setup();
    const requests = mockApi(
      routes({
        "POST /api/v1/auth/password": () => noContent(),
      })
    );

    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    expect(await screen.findByText("Şifre değiştir")).toBeInTheDocument();

    const currentInput = screen.getByLabelText("Mevcut şifre");
    const newInput = screen.getByLabelText("Yeni şifre");
    const confirmInput = screen.getByLabelText("Yeni şifreyi onayla");

    await user.type(currentInput, "correct-horse-battery");
    await user.type(newInput, "a-new-strong-password-2026");
    await user.type(confirmInput, "a-new-strong-password-2026");

    await user.click(screen.getByRole("button", { name: "Şifreyi güncelle" }));

    await waitFor(() =>
      expect(
        requests.some(
          (r) => r.path === "/api/v1/auth/password" && r.method === "POST"
        )
      ).toBe(true)
    );

    expect(await screen.findByText("Şifre başarıyla değiştirildi.")).toBeInTheDocument();
  });
});
