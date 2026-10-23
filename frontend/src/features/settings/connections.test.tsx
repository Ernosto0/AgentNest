import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SocialAccount } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const ACCOUNT_ID = "a1000000-0000-4000-8000-000000000001";
const RECONNECT = "Yeniden bağlan (simülasyon)";

function account(overrides: Partial<SocialAccount> = {}): SocialAccount {
  return {
    id: ACCOUNT_ID,
    platform: "instagram",
    provider_kind: "mock",
    username: "golkent.demo",
    status: "needs_reauth",
    capabilities: { messaging: true, publish_feed_image: true, publish_story: false },
    connection_expires_at: null,
    last_error_code: "ACCOUNT_NEEDS_REAUTH",
    degraded_until: null,
    is_simulated: true,
    ...overrides,
  };
}

function routes(ws: string, accounts: () => SocialAccount[], extra: Record<string, () => Response> = {}) {
  const base = `/api/v1/workspaces/${ws}`;
  return {
    "GET /api/v1/meta": () =>
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: accounts(), next_cursor: null }),
    ...extra,
  };
}

const PAGE = (ws: string) => `/w/${ws}/more/settings/connections`;

describe("the connections screen", () => {
  it("shows the status badge, the last error in plain language, the capabilities and the simulation badge", async () => {
    mockApi(routes(WS_GOLKENT, () => [account()]));
    renderApp(PAGE(WS_GOLKENT));

    const badge = await screen.findByTestId("account-status-badge");
    expect(badge).toHaveAttribute("data-status", "needs_reauth");
    expect(badge).toHaveTextContent("yeniden bağlanmalı");
    expect(screen.getByRole("heading", { name: "@golkent.demo" })).toBeInTheDocument();
    expect(screen.getByTestId("simulated-badge")).toBeInTheDocument();
    // The error code never reaches the reader: the catalog text does.
    const error = screen.getByTestId("account-last-error");
    expect(error).toHaveTextContent("Instagram bağlantısının yenilenmesi gerekiyor.");
    expect(error).toHaveTextContent("Instagram bağlantısı ekranını açıp yeniden bağlanın.");
    expect(error).not.toHaveTextContent("ACCOUNT_NEEDS_REAUTH");
    const capabilities = screen.getByTestId("account-capabilities");
    expect(capabilities).toHaveTextContent("Mesajlaşma, Gönderi yayınlama");
    expect(capabilities).not.toHaveTextContent("Story");
  });

  it("falls back to a generic sentence for a code the catalog does not know", async () => {
    mockApi(routes(WS_GOLKENT, () => [account({ last_error_code: "SOMETHING_NEW" })]));
    renderApp(PAGE(WS_GOLKENT));
    expect(await screen.findByTestId("account-last-error")).toHaveTextContent("Instagram ile bir sorun yaşandı.");
  });

  it("shows a connected account without an error", async () => {
    mockApi(routes(WS_GOLKENT, () => [account({ status: "connected", last_error_code: null })]));
    renderApp(PAGE(WS_GOLKENT));
    expect(await screen.findByTestId("account-status-badge")).toHaveTextContent("bağlı");
    expect(screen.getByTestId("account-last-error")).toHaveTextContent("Hata yok");
    expect(screen.queryByRole("button", { name: RECONNECT })).not.toBeInTheDocument();
  });

  it("shows degraded_until as a local time (workspace timezone, Europe/Istanbul)", async () => {
    mockApi(
      routes(WS_GOLKENT, () => [
        account({
          status: "degraded",
          last_error_code: "PROVIDER_UNAVAILABLE",
          degraded_until: "2026-10-21T10:30:00Z",
        }),
      ]),
    );
    renderApp(PAGE(WS_GOLKENT));
    const until = await screen.findByTestId("degraded-until");
    expect(until).toHaveTextContent("13:30"); // 10:30 UTC is 13:30 in Istanbul
    expect(until).not.toHaveTextContent("10:30");
  });

  it("reconnects the simulated account: posts the route and refreshes the status", async () => {
    let current = account();
    const requests = mockApi(
      routes(WS_GOLKENT, () => [current], {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/${ACCOUNT_ID}/reconnect`]: () => {
          current = account({ status: "connected", last_error_code: null });
          return json(current);
        },
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECONNECT }));

    await waitFor(() => expect(screen.getByTestId("account-status-badge")).toHaveTextContent("bağlı"));
    expect(screen.getByTestId("account-status-badge")).not.toHaveTextContent("yeniden bağlanmalı");
    expect(requests.filter((r) => r.path.endsWith("/reconnect"))).toHaveLength(1);
    expect(screen.queryByRole("button", { name: RECONNECT })).not.toBeInTheDocument();
  });

  it("leaves reconnect and disconnect to the owner", async () => {
    mockApi(routes(WS_HARBOR, () => [account()]));
    renderApp(PAGE(WS_HARBOR)); // the user is a manager here
    expect(await screen.findByTestId("account-status-badge")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: RECONNECT })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bağlantıyı kes" })).not.toBeInTheDocument();
    expect(screen.getByText("Bunu yalnızca sahip değiştirebilir.")).toBeInTheDocument();
  });

  it("asks before disconnecting, and posts only after the confirmation", async () => {
    let current = account({ status: "connected", last_error_code: null });
    const requests = mockApi(
      routes(WS_GOLKENT, () => (current.status === "disconnected" ? [] : [current]), {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/${ACCOUNT_ID}/disconnect`]: () => {
          current = account({ status: "disconnected", last_error_code: null });
          return json(current);
        },
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Bağlantıyı kes" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Bağlantıyı kesmek istiyor musunuz?")).toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/disconnect"))).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/disconnect"))).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Bağlantıyı kes" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Evet, bağlantıyı kes" }));

    expect(await screen.findByText("Bağlı bir Instagram hesabı yok.")).toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/disconnect"))).toHaveLength(1);
  });

  it("offers to connect a simulated account when there is none", async () => {
    mockApi(routes(WS_GOLKENT, () => []));
    renderApp(PAGE(WS_GOLKENT));
    expect(await screen.findByText("Bağlı bir Instagram hesabı yok.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Simüle edilmiş hesap bağla" })).toBeInTheDocument();
  });
});

describe("the menus", () => {
  it("lists the connection for everyone and the system health for the owner and manager", async () => {
    mockApi(routes(WS_GOLKENT, () => [account()]));
    renderApp(`/w/${WS_GOLKENT}/more`);
    expect(await screen.findByRole("link", { name: "Instagram bağlantısı" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
    expect(screen.getByRole("link", { name: "Sistem durumu" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/system-health`,
    );
  });

  it("links both screens from the settings page", async () => {
    mockApi(routes(WS_GOLKENT, () => [account()]));
    renderApp(`/w/${WS_GOLKENT}/more/settings`);
    expect(await screen.findByRole("link", { name: "Instagram bağlantısını yönet" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
    expect(screen.getByRole("link", { name: "Sistem durumunu gör" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/system-health`,
    );
  });
});
