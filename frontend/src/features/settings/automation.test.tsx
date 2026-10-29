import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AutomationPolicies, SocialAccount } from "@/api/types";
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
      json({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"], instagram_providers: ["mock"], mock_requires_demo_workspace: false }),
    "GET /api/v1/auth/me": () => json(ME),
    [`GET ${base}`]: () => json(workspace(ws)),
    [`GET ${base}/readiness`]: () => json(READINESS),
    [`GET ${base}/social-accounts`]: () => json({ items: accounts(), next_cursor: null }),
    [`GET ${base}/accounts/${ACCOUNT_ID}/agent`]: () => json({ controller_mode: "legacy", state: "inactive" }),
    [`GET ${base}/automation-policies`]: () =>
      json({ auto_allowed: false, items: [], readiness_level: "ready", reviewed_at: null }),
    ...extra,
  };
}

describe("the connection card", () => {
  it("shows the status and links to the connection screen, without a reconnect button", async () => {
    mockApi(routes(WS_GOLKENT, () => [account()]));
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    expect(await screen.findByTestId("account-status")).toHaveTextContent("yeniden bağlanmalı");
    expect(screen.getByRole("link", { name: "Bağlantıyı yönet" })).toHaveAttribute(
      "href",
      `/w/${WS_GOLKENT}/more/settings/connections`,
    );
    expect(screen.queryByRole("button", { name: "Yeniden bağlan (simülasyon)" })).not.toBeInTheDocument();
  });
});

describe("reviewing the automation settings", () => {
  const policies = (reviewedAt: string | null): AutomationPolicies => ({
    auto_allowed: true,
    items: [{ action_class: "reply.hours", mode: "approval" }],
    readiness_level: "ready_for_drafts",
    reviewed_at: reviewedAt,
  });

  it("offers the owner a review button until reviewed, posts once and hides it", async () => {
    let current = policies(null);
    const requests = mockApi(
      routes(WS_GOLKENT, () => [account({ status: "connected" })], {
        [`GET /api/v1/workspaces/${WS_GOLKENT}/automation-policies`]: () => json(current),
        [`POST /api/v1/workspaces/${WS_GOLKENT}/automation-policies/review`]: () => {
          current = policies("2026-10-15T12:00:00Z");
          return json(current);
        },
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Bu ayarları inceledim" }));

    await waitFor(() => expect(screen.getByText("Bu ayarları gözden geçirdiniz.")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Bu ayarları inceledim" })).not.toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/automation-policies/review"))).toHaveLength(1);
    expect(requests.filter((r) => r.method === "PUT")).toHaveLength(0);
  });

  it("does not show the button once the settings are reviewed", async () => {
    mockApi(
      routes(WS_GOLKENT, () => [account({ status: "connected" })], {
        [`GET /api/v1/workspaces/${WS_GOLKENT}/automation-policies`]: () => json(policies("2026-10-15T12:00:00Z")),
      }),
    );
    renderApp(`/w/${WS_GOLKENT}/more/automation`);
    expect(await screen.findByText("Bu ayarları gözden geçirdiniz.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bu ayarları inceledim" })).not.toBeInTheDocument();
  });

  it("leaves the button to the owner", async () => {
    mockApi(routes(WS_HARBOR, () => [account({ status: "connected" })]));
    renderApp(`/w/${WS_HARBOR}/more/automation`); // the user is a manager here
    expect(await screen.findByTestId("account-status")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bu ayarları inceledim" })).not.toBeInTheDocument();
  });
});
