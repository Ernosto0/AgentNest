import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s24");
await fs.mkdir(evidenceDir, { recursive: true });

const frontendRoot = path.resolve(__dirname, "..");
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const scenarios = [
  {
    label: "tr-phone-360",
    viewport: { width: 360, height: 740 },
    locale: "tr",
    role: "owner",
  },
  {
    label: "en-phone-390",
    viewport: { width: 390, height: 844 },
    locale: "en",
    role: "owner",
  },
  {
    label: "tr-tablet-768",
    viewport: { width: 768, height: 1024 },
    locale: "tr",
    role: "manager",
  },
  {
    label: "en-desktop-1440",
    viewport: { width: 1440, height: 900 },
    locale: "en",
    role: "staff",
  },
];

const mockAccount = {
  id: "a1000000-0000-4000-8000-000000000001",
  platform: "instagram",
  provider_kind: "mock",
  username: "golkent.demo",
  status: "connected",
  capabilities: { messaging: true, publish_feed_image: true, publish_story_image: true },
  connection_expires_at: null,
  last_error_code: null,
  degraded_until: null,
  is_simulated: true,
};

const mockMembers = [
  {
    user_id: "usr-owner",
    email: "owner@demo.local",
    display_name: "Demo Sahip",
    role: "owner",
    joined_at: "2026-01-01T00:00:00Z",
  },
  {
    user_id: "usr-staff",
    email: "staff@demo.local",
    display_name: "Ayşe Personel",
    role: "staff",
    joined_at: "2026-02-01T00:00:00Z",
  },
];

const mockInvites = [
  {
    id: "inv-1",
    role: "manager",
    expires_at: "2026-11-10T12:00:00Z",
    invite_path: "/invite/test-token",
  },
];

const results = [];

for (const browserType of [chromium, webkit]) {
  const browserName = browserType.name();
  const browser = await browserType.launch({ headless: true });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      locale: scenario.locale,
    });

    await context.addInitScript((loc) => {
      window.localStorage.setItem("agentnest.locale", loc);
    }, scenario.locale);

    const page = await context.newPage();

    await page.route("**/api/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const pathName = url.pathname;

      if (pathName === "/api/v1/meta") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            product_name: "AgentNest",
            demo_tools_enabled: true,
            llm_mode: "fake",
            supported_locales: ["tr", "en"],
            instagram_providers: ["meta", "mock"],
            mock_requires_demo_workspace: false,
          }),
        });
      }

      if (pathName === "/api/v1/auth/me") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user: {
              id: "usr-owner",
              email: "owner@demo.local",
              display_name: "Demo Sahip",
              ui_locale: scenario.locale,
            },
            csrf_token: "csrf-token-123",
            memberships: [
              {
                workspace_id: "ws-connections-test",
                role: scenario.role,
              },
            ],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-connections-test") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "ws-connections-test",
            name: "Gölkent Test",
            role: scenario.role,
            timezone: "Europe/Istanbul",
            currency: "TRY",
            business_category: "sports_facility",
            market: "TR",
            is_demo: false,
            created_at: "2026-01-01T00:00:00Z",
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-connections-test/readiness") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ready",
            missing_required_keys: [],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-connections-test/social-accounts") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [mockAccount],
            next_cursor: null,
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-connections-test/members") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: mockMembers,
            next_cursor: null,
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-connections-test/invites") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: mockInvites,
            next_cursor: null,
          }),
        });
      }

      return route.fulfill({ status: 404, body: "Not found" });
    });

    // 1. Connections Page (Route R28)
    await page.goto(`${origin}/w/ws-connections-test/more/settings/connections`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="account-status-badge"]');

    const statusBadge = await page.locator('[data-testid="account-status-badge"]').textContent();
    assert.ok(statusBadge?.length, "Account status badge should have content");

    const overflowConn = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflowConn, false, `Horizontal overflow on ${scenario.label} (connections)`);

    const axeConn = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axeConn.violations.length, 0, `Axe violations on ${scenario.label} (connections): ${JSON.stringify(axeConn.violations)}`);

    // 2. Members Page (Route R29)
    await page.goto(`${origin}/w/ws-connections-test/more/settings/members`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1");

    const overflowMem = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflowMem, false, `Horizontal overflow on ${scenario.label} (members)`);

    const axeMem = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axeMem.violations.length, 0, `Axe violations on ${scenario.label} (members): ${JSON.stringify(axeMem.violations)}`);

    const screenshotPath = path.resolve(evidenceDir, `${browserName}-${scenario.label}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    results.push({
      engine: browserName,
      scenario: scenario.label,
      passed: true,
      violations: axeConn.violations.length + axeMem.violations.length,
    });

    await context.close();
  }

  await browser.close();
}

await fs.writeFile(
  path.resolve(evidenceDir, "connections-members.json"),
  JSON.stringify(results, null, 2) + "\n",
  "utf8"
);

await server.close();
console.log("Playwright fixture scan complete: 8/8 scenarios passed with 0 Axe violations!");
