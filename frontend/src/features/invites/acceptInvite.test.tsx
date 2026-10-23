import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const TOKEN = "tok-abc-123";

function meta() {
  return json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false });
}

function acceptOk() {
  return json({ workspace_id: WS_GOLKENT, workspace_name: "Gölkent Fitness", role: "manager" });
}

describe("the invite accept page", () => {
  it("joins the workspace when already signed in", async () => {
    const requests = mockApi({
      "GET /api/v1/meta": meta,
      "GET /api/v1/auth/me": () => json(ME),
      [`GET /api/v1/workspaces/${WS_GOLKENT}`]: () => json(workspace(WS_GOLKENT)),
      [`GET /api/v1/workspaces/${WS_GOLKENT}/readiness`]: () => json(READINESS),
      "POST /api/v1/invites/accept": acceptOk,
    });
    const { router } = renderApp(`/invite/${TOKEN}`);
    const user = userEvent.setup();

    const join = await screen.findByRole("button", { name: "Katıl" });
    expect(screen.queryByLabelText("Adınız")).not.toBeInTheDocument(); // no account form
    await user.click(join);

    await waitFor(() => expect(router.state.location.pathname).toBe(`/w/${WS_GOLKENT}`));
    expect(requests.find((r) => r.path.endsWith("/invites/accept"))!.body).toEqual({ token: TOKEN });
  });

  it("creates an account and joins when signed out", async () => {
    const requests = mockApi({
      "GET /api/v1/meta": meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
      "POST /api/v1/invites/accept": acceptOk,
    });
    renderApp(`/invite/${TOKEN}`);
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "Davet" })).toBeInTheDocument();
    expect(screen.getByLabelText("Adınız")).toBeInTheDocument();
    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    expect(screen.getByLabelText("Parola")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Adınız"), "Ayşe");
    await user.type(screen.getByLabelText("E-posta"), "ayse@example.test");
    await user.type(screen.getByLabelText("Parola"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Hesap oluştur ve katıl" }));

    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith("/invites/accept"))).toBe(true),
    );
    expect(requests.find((r) => r.path.endsWith("/invites/accept"))!.body).toEqual({
      token: TOKEN,
      email: "ayse@example.test",
      display_name: "Ayşe",
      password: "correct-horse-battery",
    });
  });

  it("shows a sign-in hint when the email already exists", async () => {
    mockApi({
      "GET /api/v1/meta": meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
      "POST /api/v1/invites/accept": () =>
        problem(409, "CONFLICT_STATE", { params: { reason: "email_taken" } }),
    });
    renderApp(`/invite/${TOKEN}`);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Adınız"), "Ayşe");
    await user.type(screen.getByLabelText("E-posta"), "taken@example.test");
    await user.type(screen.getByLabelText("Parola"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Hesap oluştur ve katıl" }));

    expect(await screen.findByTestId("email-taken")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Giriş yap" })).toHaveAttribute("href", "/login");
  });

  it("shows the invalid-token error for a dead link", async () => {
    mockApi({
      "GET /api/v1/meta": meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
      "POST /api/v1/invites/accept": () => problem(400, "INVITE_INVALID"),
    });
    renderApp(`/invite/${TOKEN}`);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Adınız"), "Ayşe");
    await user.type(screen.getByLabelText("E-posta"), "ayse@example.test");
    await user.type(screen.getByLabelText("Parola"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Hesap oluştur ve katıl" }));

    expect(await screen.findByText("Bu davet bağlantısı geçersiz ya da süresi dolmuş.")).toBeInTheDocument();
  });
});
