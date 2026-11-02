import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { READINESS } from "@/test/fixtures";
import { json, mockApi, noContent, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

describe("ResetPasswordPage", () => {
  const meta = {
    "GET /api/v1/meta": () => json(READINESS),
    "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
  };

  it("renders request form and submits password reset request", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...meta,
      "POST /api/v1/auth/password-reset/request": () => json({}, 202),
    });

    renderApp("/reset-password");

    expect(await screen.findByRole("heading", { name: "Şifre sıfırlama" })).toBeInTheDocument();
    const emailInput = screen.getByLabelText("E-posta");
    await user.type(emailInput, "owner@example.com");

    const submitBtn = screen.getByRole("button", { name: "Sıfırlama bağlantısı gönder" });
    await user.click(submitBtn);

    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.path === "/api/v1/auth/password-reset/request" &&
            r.method === "POST" &&
            (r.body as { email: string }).email === "owner@example.com"
        )
      ).toBe(true)
    );

    expect(await screen.findByText("E-postanızı kontrol edin")).toBeInTheDocument();
  });

  it("renders confirm form and submits new password", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...meta,
      "POST /api/v1/auth/password-reset/confirm": () => noContent(),
    });

    renderApp("/reset-password/sample-token-12345");

    expect(await screen.findByRole("heading", { name: "Yeni şifre belirleyin" })).toBeInTheDocument();
    const newPwInput = screen.getByLabelText("Yeni şifre");
    const confirmPwInput = screen.getByLabelText("Yeni şifreyi onaylayın");

    await user.type(newPwInput, "new-secret-password-123");
    await user.type(confirmPwInput, "new-secret-password-123");

    const submitBtn = screen.getByRole("button", { name: "Şifreyi güncelle" });
    await user.click(submitBtn);

    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.path === "/api/v1/auth/password-reset/confirm" &&
            r.method === "POST" &&
            (r.body as { token: string; new_password: string }).token === "sample-token-12345" &&
            (r.body as { token: string; new_password: string }).new_password ===
              "new-secret-password-123"
        )
      ).toBe(true)
    );

    expect(await screen.findByText("Şifre güncellendi")).toBeInTheDocument();
  });
});
