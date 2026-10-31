import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME } from "@/test/fixtures";
import { json, mockApi, noContent, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

describe("LoginPage", () => {
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

  it("submits valid credentials and navigates to default destination", async () => {
    const user = userEvent.setup();
    let loggedIn = false;
    const requests = mockApi({
      ...meta,
      "GET /api/v1/auth/me": () => (loggedIn ? json(ME) : problem(401, "AUTH_REQUIRED")),
      "POST /api/v1/auth/login": () => {
        loggedIn = true;
        return noContent();
      },
    });

    const { router } = renderApp("/login");
    await user.type(await screen.findByLabelText("E-posta"), "owner@demo.local");
    await user.type(screen.getByLabelText("Parola"), "demo-password");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(requests.some((r) => r.path === "/api/v1/auth/login")).toBe(true);
  });

  it("displays notice when redirected from protected route", async () => {
    mockApi({
      ...meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
    });

    renderApp("/w/123/inbox");

    expect(await screen.findByText("Devam etmek için hesabınıza giriş yapın.")).toBeInTheDocument();
  });

  it("preserves entered inputs on login error", async () => {
    const user = userEvent.setup();
    mockApi({
      ...meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
      "POST /api/v1/auth/login": () => problem(401, "INVALID_CREDENTIALS"),
    });

    renderApp("/login");
    const emailInput = await screen.findByLabelText("E-posta");
    const passwordInput = screen.getByLabelText("Parola");

    await user.type(emailInput, "wrong@demo.local");
    await user.type(passwordInput, "wrong-password");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(emailInput).toHaveValue("wrong@demo.local");
    expect(passwordInput).toHaveValue("wrong-password");
  });
});
