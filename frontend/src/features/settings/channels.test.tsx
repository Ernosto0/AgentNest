import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChannelLink } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const LINK_ID = "c1000000-0000-4000-8000-000000000001";

function activeLink(overrides: Partial<ChannelLink> = {}): ChannelLink {
  return {
    id: LINK_ID,
    channel: "telegram",
    channel_username: "agentnest_founder",
    linked_at: "2026-11-04T00:00:00Z",
    status: "active",
    ...overrides,
  };
}

function routes(
  ws: string,
  links: () => ChannelLink[],
  extra: Record<string, () => Response> = {},
) {
  const base = `/api/v1/workspaces/${ws}`;
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
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: [], next_cursor: null }),
    [`GET ${base}/channels/links`]: () => json(links()),
    ...extra,
  };
}

const PAGE = (ws: string) => `/w/${ws}/more/settings/connections`;

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
            bot_username: "AgentNestBot",
            deep_link_url: "https://t.me/AgentNestBot?start=TEST1234",
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
      "https://t.me/AgentNestBot?start=TEST1234",
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
            bot_username: "AgentNestBot",
            deep_link_url: "https://t.me/AgentNestBot?start=COPYCODE",
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

    expect(await screen.findByText("@agentnest_founder")).toBeInTheDocument();
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

