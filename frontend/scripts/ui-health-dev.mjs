import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s25");
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
    role: "owner",
  },
];

const mockHealth = {
  generated_at: "2026-11-01T15:00:00Z",
  accounts: [
    {
      id: "a1",
      platform: "instagram",
      provider_kind: "mock",
      username: "golkent.demo",
      status: "connected",
      capabilities: { messaging: true, publish_feed_image: true },
      connection_expires_at: null,
      last_error_code: null,
      degraded_until: null,
      is_simulated: true,
    },
  ],
  operations: {
    counts: [
      { type: "send_reply", status: "success", count: 42 },
      { type: "publish_content", status: "success", count: 8 },
    ],
    latest_failures: [],
  },
  jobs: {
    queued: 0,
    oldest_queued_age_seconds: null,
    dead_24h: 0,
  },
  webhooks: {
    received_24h: 120,
    ignored_24h: 5,
    failed_24h: 0,
    signature_failures_24h_system_wide: 0,
  },
  ai: {
    runs: [
      { task: "generate_reply", status: "success", count: 35 },
      { task: "draft_content", status: "success", count: 10 },
    ],
    total: 45,
    failed: 0,
    failure_rate: 0.0,
    input_units: 15400,
    output_units: 3200,
    estimated_cost_usd: 0.045,
    budget_used: 45,
    budget_limit: 1000,
  },
};

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
                workspace_id: "ws-health-test",
                role: scenario.role,
              },
            ],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-health-test") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "ws-health-test",
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

      if (pathName === "/api/v1/workspaces/ws-health-test/readiness") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ready",
            missing_required_keys: [],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-health-test/system-health") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockHealth),
        });
      }

      if (pathName === "/api/v1/dev/scripts") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: "script-1",
              label: { tr: "Yeni Müşteri Mesajı", en: "New Customer Message" },
              customer_alias: "mert_y",
              text: "Merhaba, üyelik fiyatları nedir?",
            },
          ]),
        });
      }

      if (pathName === "/api/v1/dev/workspaces/ws-health-test/failure-rules") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      }

      if (pathName === "/api/v1/dev/jobs") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      }

      if (pathName === "/api/v1/dev/workspaces/ws-health-test/simulator/published") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      }

      return route.fulfill({ status: 404, body: "Not found" });
    });

    // 1. System Health Page (Route R30)
    await page.goto(`${origin}/w/ws-health-test/more/settings/system-health`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="health-accounts"]');

    const overflowHealth = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflowHealth, false, `Horizontal overflow on ${scenario.label} (system health)`);

    const axeHealth = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axeHealth.violations.length, 0, `Axe violations on ${scenario.label} (system health): ${JSON.stringify(axeHealth.violations)}`);

    // 2. Dev Panel (Route R31)
    await page.goto(`${origin}/w/ws-health-test/more/dev`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="dev-panel"]');

    const overflowDev = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflowDev, false, `Horizontal overflow on ${scenario.label} (dev panel)`);

    const axeDev = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axeDev.violations.length, 0, `Axe violations on ${scenario.label} (dev panel): ${JSON.stringify(axeDev.violations)}`);

    // 3. 404 Fallback Page (Route R33)
    await page.goto(`${origin}/w/ws-health-test/non-existent-page`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1");
    const h1Text = await page.locator("h1").textContent();
    assert.ok(h1Text?.includes("Bulunamadı") || h1Text?.includes("Not found"));

    const screenshotPath = path.resolve(evidenceDir, `${browserName}-${scenario.label}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    results.push({
      engine: browserName,
      scenario: scenario.label,
      passed: true,
      violations: axeHealth.violations.length + axeDev.violations.length,
    });

    await context.close();
  }

  await browser.close();
}

await fs.writeFile(
  path.resolve(evidenceDir, "health-dev.json"),
  JSON.stringify(results, null, 2) + "\n",
  "utf8"
);

await server.close();
console.log("Playwright fixture scan complete: 8/8 scenarios passed with 0 Axe violations!");
