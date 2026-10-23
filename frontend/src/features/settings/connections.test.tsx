import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SocialAccount } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, WS_PRIVATE, workspace } from "@/test/fixtures";
import { json, mockApi, problem } from "@/test/mockApi";
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
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: accounts(), next_cursor: null }),
    ...extra,
  };
}

const PAGE = (ws: string) => `/w/${ws}/more/settings/connections`;

const META = { product_name: "AgentNest", demo_tools_enabled: false, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["meta", "mock"], mock_requires_demo_workspace: false };

describe("Instagram authorization", () => {
  it.each([false, true])("uses workspace policy, independent of demo tools (demo required: %s)", async (required) => {
    mockApi(routes(WS_PRIVATE, () => [], { "GET /api/v1/meta": () => json({ ...META, mock_requires_demo_workspace: required }) }));
    renderApp(PAGE(WS_PRIVATE));
    expect(await screen.findByRole("button", { name: "Instagram ile bağlan" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Demo hesabı bağla (simülasyon)" }) !== null).toBe(!required);
  });

  it("permits a production demo workspace when mock is enabled", async () => {
    mockApi(routes(WS_GOLKENT, () => [], { "GET /api/v1/meta": () => json({ ...META, mock_requires_demo_workspace: true }) }));
    renderApp(PAGE(WS_GOLKENT));
    expect(await screen.findByRole("button", { name: "Demo hesabı bağla (simülasyon)" })).toBeEnabled();
  });

  it.each([{ providers: ["meta"] }, { providers: ["mock"] }, { providers: [] }])("offers only enabled providers: $providers", async ({ providers }) => {
    mockApi(routes(WS_GOLKENT, () => [], { "GET /api/v1/meta": () => json({ ...META, instagram_providers: providers }) }));
    renderApp(PAGE(WS_GOLKENT));
    await screen.findByText("Bağlı bir Instagram hesabı yok.");
    expect(screen.queryByRole("button", { name: "Instagram ile bağlan" }) !== null).toBe(providers.includes("meta"));
    expect(screen.queryByRole("button", { name: "Demo hesabı bağla (simülasyon)" }) !== null).toBe(providers.includes("mock"));
  });

  it.each([false, true])("redirects once for Meta connect/reconnect (%s)", async (reconnect) => {
    const assign = vi.fn(); vi.stubGlobal("location", { assign });
    const requests = mockApi(routes(WS_GOLKENT, () => reconnect ? [account({ provider_kind: "meta", is_simulated: false })] : [], {
      "GET /api/v1/meta": () => json(META),
      [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/instagram/connect`]: () => json({ authorize_url: "https://www.instagram.com/oauth/authorize?state=synthetic" }),
    }));
    renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: reconnect ? "Instagram ile bağlantıyı yenile" : "Instagram ile bağlan" });
    await user.dblClick(button);
    await waitFor(() => expect(assign).toHaveBeenCalledExactlyOnceWith("https://www.instagram.com/oauth/authorize?state=synthetic"));
    const posts = requests.filter((r) => r.path.endsWith("/instagram/connect"));
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual(reconnect ? { purpose: "reconnect", social_account_id: ACCOUNT_ID } : { purpose: "connect" });
    expect(button).toBeDisabled();
    expect(screen.queryByTestId("simulated-badge")).not.toBeInTheDocument();
  });

  it("hides Meta connection actions for a manager", async () => {
    mockApi(routes(WS_HARBOR, () => [account({ provider_kind: "meta", is_simulated: false })], { "GET /api/v1/meta": () => json(META) }));
    renderApp(PAGE(WS_HARBOR));
    await screen.findByTestId("account-status-badge");
    expect(screen.queryByRole("button", { name: /Instagram ile/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bağlantıyı kes" })).not.toBeInTheDocument();
  });

  it("keeps reconnect disabled if that provider is disabled", async () => {
    mockApi(routes(WS_GOLKENT, () => [account({ provider_kind: "meta", is_simulated: false })]));
    renderApp(PAGE(WS_GOLKENT));
    expect(await screen.findByRole("button", { name: "Instagram ile bağlantıyı yenile" })).toBeDisabled();
  });

  it("shows a safe connect failure and permits another attempt", async () => {
    mockApi(routes(WS_GOLKENT, () => [], {
      "GET /api/v1/meta": () => json(META),
      [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/instagram/connect`]: () => problem(409, "OAUTH_STATE_INVALID", { detail: "secret provider detail" }),
    }));
    renderApp(PAGE(WS_GOLKENT));
    await userEvent.click(await screen.findByRole("button", { name: "Instagram ile bağlan" }));
    expect(await screen.findByRole("alert")).not.toHaveTextContent("secret provider detail");
    expect(screen.getByRole("button", { name: "Instagram ile bağlan" })).toBeEnabled();
  });

  it.each(["connected", "error&code=ACCOUNT_MISMATCH", "error&code=OAUTH_STATE_INVALID", "error&code=UNTRUSTED_PROVIDER_TEXT"])("renders dismissible safe callback status %s and preserves other params", async (query) => {
    mockApi(routes(WS_GOLKENT, () => []));
    const { router } = renderApp(`${PAGE(WS_GOLKENT)}?keep=yes&oauth=${query}`);
    await screen.findByText("Bağlı bir Instagram hesabı yok.");
    const banner = screen.getByTestId("oauth-banner");
    expect(banner).toHaveAttribute("role", query === "connected" ? "status" : "alert");
    expect(banner).not.toHaveTextContent("UNTRUSTED_PROVIDER_TEXT");
    expect(banner).not.toHaveTextContent("ACCOUNT_MISMATCH");
    expect(banner).not.toHaveTextContent("OAUTH_STATE_INVALID");
    if (query === "connected") expect(banner).toHaveTextContent("Instagram hesabı bağlandı.");
    if (query.includes("ACCOUNT_MISMATCH")) expect(banner).toHaveTextContent("Farklı bir Instagram hesabı seçtiniz.");
    if (query.includes("OAUTH_STATE_INVALID")) expect(banner).toHaveTextContent("süresi dolmuş");
    await userEvent.click(within(banner).getByRole("button", { name: "Kapat" }));
    expect(router.state.location.search).toBe("?keep=yes");
    expect(screen.queryByTestId("oauth-banner")).not.toBeInTheDocument();
  });
});

describe("disconnect history option", () => {
  it.each([false, true])("resets the checkbox on cancel and sends the selected bool (%s)", async (erase) => {
    let current = account({ status: "connected" });
    const requests = mockApi(routes(WS_GOLKENT, () => [current], {
      [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/${ACCOUNT_ID}/disconnect`]: () => { current = account({ status: "disconnected" }); return json(current); },
    }));
    const { client } = renderApp(PAGE(WS_GOLKENT));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Bağlantıyı kes" }));
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Vazgeç" }));
    await user.click(screen.getByRole("button", { name: "Bağlantıyı kes" }));
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    if (erase) await user.click(screen.getByRole("checkbox"));
    for (const key of ["conversations", "conversation", "reply-draft", "approvals", "approval", "answers", "report", "report-items"]) {
      client.setQueryData([key, WS_GOLKENT, "cached"], { text: "old history" });
    }
    client.setQueryData(["conversation", WS_HARBOR, "cached"], { text: "other workspace" });
    client.setQueryData(["content-items", WS_GOLKENT, "cached"], []);
    await user.click(screen.getByRole("button", { name: "Evet, bağlantıyı kes" }));
    await screen.findByText("Bağlı bir Instagram hesabı yok.");
    expect(requests.find((r) => r.path.endsWith("/disconnect"))?.body).toEqual({ delete_conversation_data: erase });
    for (const key of ["conversations", "conversation", "reply-draft", "approvals", "approval", "answers", "report", "report-items"]) {
      expect(client.getQueryData([key, WS_GOLKENT, "cached"]) === undefined).toBe(erase);
      if (!erase) expect(client.getQueryState([key, WS_GOLKENT, "cached"])?.isInvalidated).toBe(true);
    }
    expect(client.getQueryState(["content-items", WS_GOLKENT, "cached"])?.isInvalidated).toBe(true);
    expect(client.getQueryData(["conversation", WS_HARBOR, "cached"])).toEqual({ text: "other workspace" });
  });

  it("keeps a failed disconnect visible and actionable inside the sheet", async () => {
    mockApi(routes(WS_GOLKENT, () => [account()], {
      [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/${ACCOUNT_ID}/disconnect`]: () => problem(409, "CONFLICT_STATE"),
    }));
    renderApp(PAGE(WS_GOLKENT));
    await userEvent.click(await screen.findByRole("button", { name: "Bağlantıyı kes" }));
    await userEvent.click(screen.getByRole("button", { name: "Evet, bağlantıyı kes" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toBeVisible();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(within(dialog).getByRole("button", { name: "Evet, bağlantıyı kes" })).toBeEnabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

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
    expect(screen.getByRole("button", { name: "Demo hesabı bağla (simülasyon)" })).toBeInTheDocument();
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
