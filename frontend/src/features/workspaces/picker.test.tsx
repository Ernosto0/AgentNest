import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, WS_GOLKENT } from "@/test/fixtures";
import { json, mockApi, noContent } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

describe("WorkspacePickerPage", () => {
  const meta = {
    "GET /api/v1/meta": () =>
      json({
        product_name: "AgentNest",
        demo_tools_enabled: true,
        llm_mode: "fake",
        supported_locales: ["tr", "en"],
        instagram_providers: ["mock"],
        mock_requires_demo_workspace: false,
      }),
  };

  it("lists memberships with roles and demo badge", async () => {
    mockApi({
      ...meta,
      "GET /api/v1/auth/me": () =>
        json({
          ...ME,
          memberships: [
            {
              workspace_id: WS_GOLKENT,
              workspace_name: "Gölkent Fitness with an intentionally very long workspace name",
              role: "owner",
              is_demo: true,
            },
            {
              workspace_id: "22222222-2222-4222-8222-222222222222",
              workspace_name: "Second Studio",
              role: "staff",
              is_demo: false,
            },
          ],
        }),
    });

    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Çalışma alanı seçin" })).toBeInTheDocument();
    expect(
      screen.getByText("Gölkent Fitness with an intentionally very long workspace name"),
    ).toBeInTheDocument();
    expect(screen.getByText("Second Studio")).toBeInTheDocument();
    expect(screen.getByText("Sahip")).toBeInTheDocument();
    expect(screen.getByText("Personel")).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Çalışma alanı oluştur/i })).toHaveAttribute(
      "href",
      "/workspaces/new",
    );
  });

  it("shows empty state when user has no memberships", async () => {
    mockApi({
      ...meta,
      "GET /api/v1/auth/me": () =>
        json({
          ...ME,
          memberships: [],
        }),
    });

    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Çalışma alanı seçin" })).toBeInTheDocument();
    expect(screen.getByText("Henüz bir çalışma alanınız yok.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Çalışma alanı oluştur/i })).toHaveAttribute(
      "href",
      "/workspaces/new",
    );
  });

  it("handles sign out from header action", async () => {
    const user = userEvent.setup();
    let loggedOut = false;
    const requests = mockApi({
      ...meta,
      "GET /api/v1/auth/me": () => (loggedOut ? json(null) : json(ME)),
      "POST /api/v1/auth/logout": () => {
        loggedOut = true;
        return noContent();
      },
    });

    const { router } = renderApp("/");
    expect(await screen.findByRole("heading", { name: "Çalışma alanı seçin" })).toBeInTheDocument();
    const signOutBtn = screen.getByRole("button", { name: "Çıkış yap" });
    await user.click(signOutBtn);

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(requests.some((r) => r.path === "/api/v1/auth/logout")).toBe(true);
  });
});
