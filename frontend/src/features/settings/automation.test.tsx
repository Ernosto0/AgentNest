import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SocialAccount } from "@/api/types";
import { ME, READINESS, WS_GOLKENT, WS_HARBOR, workspace } from "@/test/fixtures";
import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const ACCOUNT_ID = "a1000000-0000-4000-8000-000000000001";

function account(overrides: Partial<SocialAccount> = {}): SocialAccount {
  return {
    id: ACCOUNT_ID,
    platform: "instagram",
    provider_kind: "mock",
    username: "golkent.demo",
    status: "needs_reauth",
    capabilities: { messaging: true },
    connection_expires_at: null,
    last_error_code: "ACCOUNT_NEEDS_REAUTH",
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
    [`GET ${base}/automation-policies`]: () =>
      json({ auto_allowed: false, items: [], readiness_level: "ready", reviewed_at: null }),
    ...extra,
  };
}

describe("reconnecting the simulated account", () => {
  it("offers the button when the connection is lost, posts the reconnect and refreshes the status", async () => {
    let current = account();
    const requests = mockApi(
      routes(WS_GOLKENT, () => [current], {
        [`POST /api/v1/workspaces/${WS_GOLKENT}/social-accounts/${ACCOUNT_ID}/reconnect`]: () => {
          current = account({ status: "connected", last_error_code: null });
          return json(current);
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    const user = userEvent.setup();

    expect(await screen.findByTestId("account-status")).toHaveTextContent("yeniden bağlanmalı");
    await user.click(await screen.findByRole("button", { name: "Yeniden bağlan (simülasyon)" }));

    await waitFor(() => expect(screen.getByTestId("account-status")).toHaveTextContent("bağlı"));
    expect(screen.getByTestId("account-status")).not.toHaveTextContent("yeniden bağlanmalı");
    expect(requests.filter((r) => r.path.endsWith("/reconnect"))).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Yeniden bağlan (simülasyon)" })).not.toBeInTheDocument();
  });

  it("shows no button while the account is connected", async () => {
    mockApi(routes(WS_GOLKENT, () => [account({ status: "connected" })]));
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    expect(await screen.findByTestId("account-status")).toHaveTextContent("bağlı");
    expect(screen.queryByRole("button", { name: "Yeniden bağlan (simülasyon)" })).not.toBeInTheDocument();
  });

  it("leaves the button to the owner", async () => {
    mockApi(routes(WS_HARBOR, () => [account()]));
    renderApp(`/w/${WS_HARBOR}/more/automation`); // the user is a manager here
    expect(await screen.findByTestId("account-status")).toHaveTextContent("yeniden bağlanmalı");
    expect(screen.queryByRole("button", { name: "Yeniden bağlan (simülasyon)" })).not.toBeInTheDocument();
  });
});
