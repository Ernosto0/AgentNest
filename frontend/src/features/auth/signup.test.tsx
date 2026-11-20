import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME } from "@/test/fixtures";
import { json, mockApi, noContent, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const metaWith = (signup_enabled: boolean) => ({
  "GET /api/v1/meta": () =>
    json({
      product_name: "Pivoris",
      demo_tools_enabled: false,
      llm_mode: "fake",
      supported_locales: ["tr", "en"],
      instagram_providers: ["mock"],
      mock_requires_demo_workspace: false,
      signup_enabled,
      terms_version: "2026-11-16",
    }),
});
const signedOut = { "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED") };
const unverifiedMe = { ...ME, user: { ...ME.user, email_verified: false }, memberships: [] };

describe("signup", () => {
  it("shows the signup link on the login page only when signup is enabled", async () => {
    mockApi({ ...metaWith(true), ...signedOut });
    const { unmount } = renderApp("/login");
    expect(await screen.findByRole("link", { name: "Hesap oluştur" })).toBeInTheDocument();
    unmount();

    mockApi({ ...metaWith(false), ...signedOut });
    renderApp("/login");
    await screen.findByLabelText("E-posta");
    expect(screen.queryByRole("link", { name: "Hesap oluştur" })).not.toBeInTheDocument();
  });

  it("sends the accepted terms version and moves on to the check-your-email page", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...metaWith(true),
      ...signedOut,
      "POST /api/v1/auth/register": () => new Response(null, { status: 202 }),
    });
    const { router } = renderApp("/signup");

    await user.type(await screen.findByLabelText("Adınız"), "Ayşe Kaya");
    await user.type(screen.getByLabelText("E-posta"), "ayse@example.com");
    await user.type(screen.getByLabelText("Parola"), "a-long-enough-password");
    const submit = screen.getByRole("button", { name: "Hesap oluştur" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(submit);

    await waitFor(() => expect(router.state.location.pathname).toBe("/check-email"));
    const register = requests.find((r) => r.path === "/api/v1/auth/register");
    expect(register?.body).toEqual({
      email: "ayse@example.com",
      password: "a-long-enough-password",
      name: "Ayşe Kaya",
      accepted_terms_version: "2026-11-16",
      ui_locale: "tr",
    });
    expect(await screen.findByLabelText("E-posta")).toHaveValue("ayse@example.com");
  });

  it("redirects to the login page when signup is disabled", async () => {
    mockApi({ ...metaWith(false), ...signedOut });
    const { router } = renderApp("/signup");
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });

  it("resends the verification email from the check-your-email page", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...metaWith(true),
      ...signedOut,
      "POST /api/v1/auth/resend-verification": () => new Response(null, { status: 202 }),
    });
    renderApp("/check-email");
    await user.type(await screen.findByLabelText("E-posta"), "ayse@example.com");
    await user.click(screen.getByRole("button", { name: "Doğrulama e-postasını yeniden gönder" }));
    expect(await screen.findByText(/yeni bağlantı gönderildi/)).toBeInTheDocument();
    expect(requests.find((r) => r.path === "/api/v1/auth/resend-verification")?.body).toEqual({
      email: "ayse@example.com",
    });
  });

  it("keeps an unverified session on the check-your-email page", async () => {
    mockApi({ ...metaWith(true), "GET /api/v1/auth/me": () => json(unverifiedMe) });
    const { router } = renderApp("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/check-email"));
    expect(await screen.findByLabelText("E-posta")).toHaveValue(ME.user.email);
    expect(await screen.findByRole("button", { name: "Çıkış yap" })).toBeInTheDocument();
  });

  it("verifies the email only after the button is pressed and then offers sign-in", async () => {
    const user = userEvent.setup();
    const requests = mockApi({
      ...metaWith(true),
      ...signedOut,
      "POST /api/v1/auth/verify-email": () => noContent(),
    });
    renderApp("/verify-email/abc.def");
    const button = await screen.findByRole("button", { name: "E-postayı doğrula" });
    expect(requests.some((r) => r.path === "/api/v1/auth/verify-email")).toBe(false);
    await user.click(button);
    expect(await screen.findByText("E-postanız doğrulandı.")).toBeInTheDocument();
    expect(requests.find((r) => r.path === "/api/v1/auth/verify-email")?.body).toEqual({
      token: "abc.def",
    });
    expect(screen.getByRole("link", { name: "Giriş yap ve çalışma alanını oluştur" })).toBeInTheDocument();
  });

  it("explains an invalid or expired verification link", async () => {
    const user = userEvent.setup();
    mockApi({
      ...metaWith(true),
      ...signedOut,
      "POST /api/v1/auth/verify-email": () => problem(400, "EMAIL_VERIFICATION_TOKEN_INVALID"),
    });
    renderApp("/verify-email/bad");
    await user.click(await screen.findByRole("button", { name: "E-postayı doğrula" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/geçersiz veya süresi dolmuş/);
  });
});
