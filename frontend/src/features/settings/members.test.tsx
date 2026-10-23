import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Invite, Member } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi, problem, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const OWNER_ID = ME.user.id;
const STAFF_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function member(overrides: Partial<Member> = {}): Member {
  return {
    user_id: OWNER_ID,
    email: "owner@demo.local",
    display_name: "Demo Sahip",
    role: "owner",
    joined_at: "2026-10-15T12:00:00Z",
    ...overrides,
  };
}

function routes(
  ws: string,
  members: () => Member[],
  invites: () => { id: string; role: string; expires_at: string }[],
  extra: Record<string, (request: RecordedRequest) => Response> = {},
) {
  const base = `/api/v1/workspaces/${ws}`;
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/members`]: () => json({ items: members(), next_cursor: null }),
    [`GET ${base}/invites`]: () => json({ items: invites(), next_cursor: null }),
    ...extra,
  };
}

const PAGE = (ws: string) => `/w/${ws}/more/settings/members`;

describe("the members screen", () => {
  it("lists members with their roles", async () => {
    mockApi(
      routes(WS_GOLKENT, () => [member(), member({ user_id: STAFF_ID, display_name: "Ayşe", role: "staff", email: "staff@demo.local" })], () => []),
    );
    renderApp(PAGE(WS_GOLKENT));

    expect(await screen.findByText("Demo Sahip")).toBeInTheDocument();
    expect(screen.getByText("Ayşe")).toBeInTheDocument();
    // The owner sees a role select for every member.
    expect(screen.getByTestId(`role-select-${OWNER_ID}`)).toHaveValue("owner");
    expect(screen.getByTestId(`role-select-${STAFF_ID}`)).toHaveValue("staff");
  });

  it("changes a role through the select", async () => {
    let staff = member({ user_id: STAFF_ID, display_name: "Ayşe", role: "staff", email: "staff@demo.local" });
    const requests = mockApi(
      routes(WS_GOLKENT, () => [member(), staff], () => [], {
        [`PATCH /api/v1/workspaces/${WS_GOLKENT}/members/${STAFF_ID}`]: (request) => {
          staff = { ...staff, role: (request.body as { role: "manager" }).role };
          return json(staff);
        },
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByTestId(`role-select-${STAFF_ID}`), "manager");

    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith(`/members/${STAFF_ID}`) && r.method === "PATCH")).toBe(true),
    );
    expect(requests.find((r) => r.method === "PATCH")!.body).toEqual({ role: "manager" });
  });

  it("shows the last-owner error text when the owner demotes the only owner", async () => {
    mockApi(
      routes(WS_GOLKENT, () => [member()], () => [], {
        [`PATCH /api/v1/workspaces/${WS_GOLKENT}/members/${OWNER_ID}`]: () => problem(409, "LAST_OWNER_REQUIRED"),
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByTestId(`role-select-${OWNER_ID}`), "manager");

    expect(await screen.findByText("Çalışma alanında en az bir sahip kalmalı.")).toBeInTheDocument();
  });

  it("leaves the management controls to the owner only", async () => {
    mockApi(routes(WS_HARBOR, () => [member({ user_id: ME.user.id, role: "manager" })], () => []));
    renderApp(PAGE(WS_HARBOR));
    expect(await screen.findByText("Demo Sahip")).toBeInTheDocument();
    expect(screen.queryByTestId(`role-select-${OWNER_ID}`)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Üye davet et" })).not.toBeInTheDocument();
  });

  it("revokes a pending invite", async () => {
    const inviteId = "b0000000-0000-4000-8000-000000000001";
    let invites = [{ id: inviteId, role: "manager", expires_at: "2026-10-22T12:00:00Z" }];
    const requests = mockApi(
      routes(WS_GOLKENT, () => [member()], () => invites, {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/invites/${inviteId}/revoke`]: () => {
          invites = [];
          return new Response(null, { status: 204 });
        },
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    expect(await screen.findByText(/Bekleyen davetler/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Geri al" }));

    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/revoke"))).toBe(true));
    expect(await screen.findByText("Bekleyen davet yok.")).toBeInTheDocument();
  });

  it("the invite sheet shows the URL and the QR code", async () => {
    const invite: Invite = {
      id: "c0000000-0000-4000-8000-000000000001",
      role: "manager",
      expires_at: "2026-10-22T12:00:00Z",
      invite_path: "/invite/tok-abc-123",
      invite_url: "http://localhost:8000/invite/tok-abc-123",
      created_at: "2026-10-15T12:00:00Z",
    };
    mockApi(
      routes(WS_GOLKENT, () => [member()], () => [], {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/invites`]: () => json(invite, 201),
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Üye davet et" }));
    await user.click(await screen.findByRole("button", { name: "Davet oluştur" }));

    const url = await screen.findByTestId("invite-url");
    expect(url).toHaveTextContent("/invite/tok-abc-123");
    expect(url.textContent).toContain(window.location.origin); // the LAN-safe origin, not APP_BASE_URL
    expect(await screen.findByTestId("invite-qr")).toBeInTheDocument();
  });

  it("removes a member after confirmation", async () => {
    const requests = mockApi(
      routes(WS_GOLKENT, () => [member(), member({ user_id: STAFF_ID, display_name: "Ayşe", role: "staff" })], () => [], {
        [`DELETE /api/v1/workspaces/${WS_GOLKENT}/members/${STAFF_ID}`]: () => new Response(null, { status: 204 }),
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    const row = (await screen.findByText("Ayşe")).closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Üyeyi çıkar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Üyeyi çıkarmak istiyor musunuz?")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Evet, çıkar" }));
    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith(`/members/${STAFF_ID}`) && r.method === "DELETE")).toBe(true),
    );
  });
});
