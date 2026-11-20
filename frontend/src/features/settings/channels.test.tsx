import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChannelLink } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi, type RecordedRequest } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const LINK_ID = "c1000000-0000-4000-8000-000000000001";

function activeLink(overrides: Partial<ChannelLink> = {}): ChannelLink {
  return {
    id: LINK_ID,
    channel: "telegram",
    channel_username: "pivoris_founder",
    linked_at: "2026-11-04T00:00:00Z",
    status: "active",
    ...overrides,
  };
}

function routes(
  ws: string,
  links: () => ChannelLink[],
  extra: Record<string, (req: RecordedRequest) => Response> = {},
) {
  const base = `/api/v1/workspaces/${ws}`;
  return {
    "GET /api/v1/meta": () =>
      json({
        product_name: "Pivoris",
        demo_tools_enabled: true,
        llm_mode: "fake",
        supported_locales: ["tr", "en"],
        instagram_providers: ["mock"],
        mock_requires_demo_workspace: false,
      }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${base}/calendar`]: () => json({ items: [] }),
    [`GET ${base}/channels/links`]: () => json(links()),
    ...extra,
  };
}

const PAGE = (ws: string) => `/w/${ws}/more/settings/connections`;

describe("WhatsApp linking", () => {
  const availability = (whatsapp: boolean) => ({
    [`GET /api/v1/workspaces/${WS_GOLKENT}/channels/availability`]: () => json({ whatsapp }),
  });

  it("hides WhatsApp when the server has no credentials for it", async () => {
    const requests = mockApi(routes(WS_GOLKENT, () => [], availability(false)));
    renderApp(PAGE(WS_GOLKENT));
    await screen.findByTestId("channel-status-badge");
    await waitFor(() =>
      expect(requests.some((r) => r.path.endsWith("/channels/availability"))).toBe(true),
    );
    expect(screen.queryByTestId("whatsapp-status-badge")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "WhatsApp'ı bağla" })).not.toBeInTheDocument();
  });

  it("creates a WhatsApp code and shows its business-number deep link", async () => {
    const user = userEvent.setup();
    const requests = mockApi(
      routes(WS_GOLKENT, () => [], {
        ...availability(true),
        [`POST /api/v1/workspaces/${WS_GOLKENT}/channels/link-code`]: () =>
          json({
            channel: "whatsapp",
            code: "WAPP1234",
            expires_at: new Date(Date.now() + 900000).toISOString(),
            bot_username: null,
            whatsapp_number: "905551112233",
            deep_link_url: "https://wa.me/905551112233?text=WAPP1234",
          }),
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    await user.click(await screen.findByRole("button", { name: "WhatsApp'ı bağla" }));
    expect(await screen.findByTestId("channel-link-code-display")).toHaveTextContent("WAPP1234");
    expect(screen.getByRole("link", { name: "WhatsApp'ta aç" })).toHaveAttribute(
      "href",
      "https://wa.me/905551112233?text=WAPP1234",
    );
    expect(
      requests.find((r) => r.method === "POST" && r.path.endsWith("/channels/link-code"))?.body,
    ).toEqual({ channel: "whatsapp" });
    expect(screen.queryByRole("link", { name: "Telegram'da aç" })).not.toBeInTheDocument();
  });

  it("unlinks WhatsApp while preserving Telegram", async () => {
    const user = userEvent.setup();
    const waId = "c1000000-0000-4000-8000-000000000002";
    let links = [activeLink(), activeLink({ id: waId, channel: "whatsapp", channel_username: null })];
    mockApi(
      routes(WS_GOLKENT, () => links, {
        ...availability(true),
        [`DELETE /api/v1/workspaces/${WS_GOLKENT}/channels/links/${waId}`]: () => {
          links = links.filter((link) => link.id !== waId);
          return new Response(null, { status: 204 });
        },
      }),
    );
    renderApp(PAGE(WS_GOLKENT));
    await waitFor(() =>
      expect(screen.getByTestId("whatsapp-status-badge")).toHaveAttribute("data-status", "connected"),
    );
    await user.click(screen.getByRole("button", { name: "WhatsApp bağlantısını kes" }));
    expect(await screen.findByText("WhatsApp bağlantısını kaldır")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evet, bağlantıyı kaldır" }));
    await waitFor(() =>
      expect(screen.getByTestId("whatsapp-status-badge")).toHaveAttribute("data-status", "unlinked"),
    );
    expect(screen.getByTestId("channel-status-badge")).toHaveAttribute("data-status", "connected");
  });
});

describe("Owner Messaging Channel Settings (Telegram)", () => {
  it("renders unlinked state with Connect button when no channel is linked", async () => {
    mockApi(routes(WS_GOLKENT, () => []));
    renderApp(PAGE(WS_GOLKENT));

    expect(await screen.findByText("Telegram bağlantısı")).toBeInTheDocument();
    const statusBadge = await screen.findByTestId("channel-status-badge");
    expect(statusBadge).toHaveAttribute("data-status", "unlinked");
    expect(screen.getByRole("button", { name: "Telegram'ı bağla" })).toBeInTheDocument();
  });

  it("opens modal with 8-character link code, timer, and deep link on connect", async () => {
    const user = userEvent.setup();
    let codeGenerated = false;

    mockApi(
      routes(WS_GOLKENT, () => [], {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/channels/link-code`]: () => {
          codeGenerated = true;
          return json({
            code: "TEST1234",
            expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
            bot_username: "PivorisBot",
            deep_link_url: "https://t.me/PivorisBot?start=TEST1234",
          });
        },
      }),
    );

    renderApp(PAGE(WS_GOLKENT));

    const connectBtn = await screen.findByRole("button", { name: "Telegram'ı bağla" });
    await user.click(connectBtn);

    expect(codeGenerated).toBe(true);
    expect(await screen.findByText("Telegram hesabınızı bağlayın")).toBeInTheDocument();
    expect(screen.getByTestId("channel-link-code-display")).toHaveTextContent("TEST1234");
    expect(screen.getByTestId("channel-link-timer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Telegram'da aç" })).toHaveAttribute(
      "href",
      "https://t.me/PivorisBot?start=TEST1234",
    );
  });

  it("copies link code to clipboard when copy button is pressed", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText },
    });

    mockApi(
      routes(WS_GOLKENT, () => [], {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/channels/link-code`]: () =>
          json({
            code: "COPYCODE",
            expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
            bot_username: "PivorisBot",
            deep_link_url: "https://t.me/PivorisBot?start=COPYCODE",
          }),
      }),
    );

    renderApp(PAGE(WS_GOLKENT));

    const connectBtn = await screen.findByRole("button", { name: "Telegram'ı bağla" });
    await user.click(connectBtn);

    const copyBtn = await screen.findByRole("button", { name: "Kodu kopyala" });
    await user.click(copyBtn);

    expect(writeText).toHaveBeenCalledWith("COPYCODE");
    expect(await screen.findByText("Kopyalandı!")).toBeInTheDocument();
  });

  it("renders connected state and handles disconnect confirmation flow", async () => {
    const user = userEvent.setup();
    let currentLinks = [activeLink()];
    let deleteCalled = false;

    mockApi(
      routes(
        WS_GOLKENT,
        () => currentLinks,
        {
          [`DELETE /api/v1/workspaces/${WS_GOLKENT}/channels/links/${LINK_ID}`]: () => {
            deleteCalled = true;
            currentLinks = [];
            return new Response(null, { status: 204 });
          },
        },
      ),
    );

    renderApp(PAGE(WS_GOLKENT));

    expect(await screen.findByText("@pivoris_founder")).toBeInTheDocument();
    const statusBadge = await screen.findByTestId("channel-status-badge");
    expect(statusBadge).toHaveAttribute("data-status", "connected");

    const disconnectBtn = screen.getByRole("button", { name: "Bağlantıyı kaldır" });
    await user.click(disconnectBtn);

    // Confirmation bottom sheet
    expect(await screen.findByText("Telegram bağlantısını kaldır")).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: "Evet, bağlantıyı kaldır" });
    await user.click(confirmBtn);

    await waitFor(() => expect(deleteCalled).toBe(true));
  });
});

describe("Notification Channel Preferences (Explicit Channel Choice)", () => {
  const basePreferences = {
    telegram: true,
    whatsapp: false,
    app_only: false,
    channels: {
      telegram: {
        status: "connected",
        enabled: true,
        configured: true,
        linked: true,
        last_error: null,
      },
      whatsapp: {
        status: "unlinked",
        enabled: false,
        configured: true,
        linked: false,
        last_error: null,
      },
    },
  };

  it("renders explicit channel preferences and switches to app-only", async () => {
    const user = userEvent.setup();
    let currentPrefs = { ...basePreferences };
    let putBody: unknown = null;

    mockApi(
      routes(WS_GOLKENT, () => [activeLink()], {
        [`GET /api/v1/workspaces/${WS_GOLKENT}/channels/preferences`]: () => json(currentPrefs),
        [`PUT /api/v1/workspaces/${WS_GOLKENT}/channels/preferences`]: (req) => {
          putBody = req.body;
          currentPrefs = {
            ...currentPrefs,
            telegram: false,
            whatsapp: false,
            app_only: true,
            channels: {
              ...currentPrefs.channels,
              telegram: { ...currentPrefs.channels.telegram, status: "disabled", enabled: false },
            },
          };
          return json(currentPrefs);
        },
      }),
    );

    renderApp(PAGE(WS_GOLKENT));

    expect(await screen.findByText("Bildirim kanalları")).toBeInTheDocument();
    const appOnlyBtn = screen.getByTestId("app-only-button");
    expect(appOnlyBtn).toBeInTheDocument();

    await user.click(appOnlyBtn);

    await waitFor(() => expect(putBody).toEqual({ app_only: true }));
    expect(await screen.findByTestId("app-only-active-notice")).toHaveTextContent(
      "Yalnızca uygulama içi bildirimler etkin",
    );
    expect(screen.getByTestId("channel-status-badge")).toHaveAttribute("data-status", "disabled");
  });

  it("truthfully renders delivery-failure status when a channel has a delivery error", async () => {
    mockApi(
      routes(WS_GOLKENT, () => [activeLink()], {
        [`GET /api/v1/workspaces/${WS_GOLKENT}/channels/preferences`]: () =>
          json({
            ...basePreferences,
            channels: {
              ...basePreferences.channels,
              telegram: {
                status: "delivery_failure",
                enabled: true,
                configured: true,
                linked: true,
                last_error: "ambiguous_transport_timeout",
              },
            },
          }),
      }),
    );

    renderApp(PAGE(WS_GOLKENT));

    await waitFor(() => {
      const statusBadge = screen.getByTestId("channel-status-badge");
      expect(statusBadge).toHaveAttribute("data-status", "delivery_failure");
    });
    const statusBadge = screen.getByTestId("channel-status-badge");
    expect(statusBadge).toHaveTextContent("Teslimat hatası");
    expect(await screen.findByTestId("telegram-delivery-failure-note")).toHaveTextContent(
      "Son bildirim bu kanala iletilemedi.",
    );
  });

  it("allows toggling an individual channel on and off", async () => {
    const user = userEvent.setup();
    let putBody: unknown = null;

    mockApi(
      routes(WS_GOLKENT, () => [activeLink()], {
        [`GET /api/v1/workspaces/${WS_GOLKENT}/channels/preferences`]: () => json(basePreferences),
        [`PUT /api/v1/workspaces/${WS_GOLKENT}/channels/preferences`]: (req) => {
          putBody = req.body;
          return json({
            ...basePreferences,
            telegram: false,
            channels: {
              ...basePreferences.channels,
              telegram: { ...basePreferences.channels.telegram, status: "disabled", enabled: false },
            },
          });
        },
      }),
    );

    renderApp(PAGE(WS_GOLKENT));

    const toggle = await screen.findByTestId("toggle-telegram-preference");
    expect(toggle).toBeChecked();

    await user.click(toggle);

    await waitFor(() => expect(putBody).toEqual({ telegram: false }));
  });
});

