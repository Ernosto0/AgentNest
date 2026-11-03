import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { json, mockApi, problem } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

describe("Legal Pages", () => {
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

  it("renders Privacy Policy page publicly with key sections", async () => {
    mockApi({
      ...meta,
    });

    renderApp("/privacy");

    expect(await screen.findByRole("heading", { name: "Gizlilik Politikası" })).toBeInTheDocument();
    expect(screen.getByText("Veri Sorumlusu ve Roller")).toBeInTheDocument();
    expect(screen.getByText("Güvenlik ve İzolasyon")).toBeInTheDocument();
    expect(screen.getByText("Veri Saklama ve İmha")).toBeInTheDocument();
  });

  it("renders Data Deletion page and queries confirmation code successfully", async () => {
    const user = userEvent.setup();
    mockApi({
      ...meta,
      "GET /api/v1/webhooks/meta/data-deletion/del_test123": () =>
        json({
          confirmation_code: "del_test123",
          status: "completed",
          requested_at: "2026-11-03T12:00:00Z",
          completed_at: "2026-11-03T12:05:00Z",
        }),
    });

    renderApp("/data-deletion");

    expect(await screen.findByRole("heading", { name: "Veri Silme Talimatları" })).toBeInTheDocument();

    const input = screen.getByPlaceholderText("Onay kodunu girin (örn. del_...)");
    await user.type(input, "del_test123");
    await user.click(screen.getByRole("button", { name: "Durumu Sorgula" }));

    expect(await screen.findByText("Tamamlandı: Verileriniz kalıcı olarak silinmiştir.")).toBeInTheDocument();
    expect(screen.getByText("del_test123")).toBeInTheDocument();
  });

  it("shows not-found message when confirmation code does not exist", async () => {
    const user = userEvent.setup();
    mockApi({
      ...meta,
      "GET /api/v1/webhooks/meta/data-deletion/del_missing": () =>
        problem(404, "NOT_FOUND"),
    });

    renderApp("/data-deletion");

    const input = await screen.findByPlaceholderText("Onay kodunu girin (örn. del_...)");
    await user.type(input, "del_missing");
    await user.click(screen.getByRole("button", { name: "Durumu Sorgula" }));

    expect(await screen.findByText("Onay kodu bulunamadı veya süresi doldu.")).toBeInTheDocument();
  });

  it("LoginPage links to Privacy Policy and Data Deletion pages", async () => {
    mockApi({
      ...meta,
      "GET /api/v1/auth/me": () => problem(401, "AUTH_REQUIRED"),
    });

    renderApp("/login");

    const privacyLink = await screen.findByRole("link", { name: "Gizlilik Politikası" });
    const deletionLink = screen.getByRole("link", { name: "Veri Silme Talimatları" });

    expect(privacyLink).toHaveAttribute("href", "/privacy");
    expect(deletionLink).toHaveAttribute("href", "/data-deletion");
  });
});
