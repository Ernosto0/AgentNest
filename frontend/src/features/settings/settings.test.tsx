import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, noContent, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const STAFF_ME = {
  ...ME,
  memberships: ME.memberships.map((m) =>
    m.workspace_id === WS_GOLKENT ? { ...m, role: "staff" as const } : m,
  ),
};

function routes(extra: Record<string, (request: RecordedRequest) => Response> = {}, me = ME) {
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
    "GET /api/v1/auth/me": () => json(me),
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
    [`GET ${base}`]: () => json(workspace(WS_GOLKENT)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    ...extra,
  };
}

describe("SettingsPage", () => {
  it("renders user identity, workspace details, and role-authorized links for owner", async () => {
    mockApi(routes());
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const main = within(await screen.findByRole("main"));
    expect(main.getByRole("heading", { name: "Ayarlar", level: 1 })).toBeInTheDocument();
    expect(main.getByText("Demo Sahip")).toBeInTheDocument();
    expect(main.getByText("owner@demo.local")).toBeInTheDocument();
    expect(main.getByText("Sahip")).toBeInTheDocument();

    // Read-only workspace info
    expect(main.getAllByText("Gölkent Fitness").length).toBeGreaterThanOrEqual(1);
    expect(main.getByText("tr · TRY")).toBeInTheDocument();
    expect(main.getByText("Europe/Istanbul")).toBeInTheDocument();

    // Management links for owner
    expect(main.getByRole("link", { name: /Instagram bağlantısını yönet/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
    expect(main.getByRole("link", { name: /Ekip üyelerini yönet/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/members`,
    );
    expect(main.getByRole("link", { name: /Sistem durumunu gör/ })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/system-health`,
    );

    // Security & privacy informational text
    expect(main.getByText("Güvenlik ve oturumlar")).toBeInTheDocument();
    expect(main.getByText("Gizlilik ve veri hakları")).toBeInTheDocument();
  });

  it("hides system health link for staff members", async () => {
    mockApi(routes({}, STAFF_ME));
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    expect(await screen.findByRole("heading", { name: "Ayarlar", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Personel")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Instagram bağlantısını yönet/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ekip üyelerini yönet/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Sistem durumunu gör/ })).toBeNull();
  });

  it("triggers language change mutation when selecting language", async () => {
    const requests = mockApi(
      routes({
        "PATCH /api/v1/auth/me": (req) => {
          const body = (typeof req.body === "string" ? JSON.parse(req.body) : req.body ?? {}) as { ui_locale?: string };
          return json({ ...ME, user: { ...ME.user, ui_locale: body.ui_locale ?? "en" } });
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const enButton = await screen.findByRole("button", { name: "English" });
    await userEvent.setup().click(enButton);

    await waitFor(() => {
      expect(
        requests.some((r) => r.path === "/api/v1/auth/me" && r.method === "PATCH"),
      ).toBe(true);
    });
  });

  it("signs out and redirects to login", async () => {
    let loggedOut = false;
    const requests = mockApi(
      routes({
        "POST /api/v1/auth/logout": () => {
          loggedOut = true;
          return noContent();
        },
      }),
    );
    const { router } = renderApp(`/w/${WS_GOLKENT}/more/settings`);

    const signOutBtn = await screen.findByRole("button", { name: "Oturumu kapat" });
    await userEvent.setup().click(signOutBtn);

    await waitFor(() => expect(loggedOut).toBe(true));
    await waitFor(() => expect(requests.some((r) => r.path === "/api/v1/auth/logout")).toBe(true));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });
});
