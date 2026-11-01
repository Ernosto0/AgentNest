import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s23");
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
            instagram_providers: ["mock"],
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
              id: "usr-1",
              email: "operator@golkent.test",
              display_name: "Demo Operator",
              ui_locale: scenario.locale,
            },
            csrf_token: "csrf-token-123",
            memberships: [
              {
                workspace_id: "ws-settings-test",
                role: scenario.role,
              },
            ],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-settings-test") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "ws-settings-test",
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

      if (pathName === "/api/v1/workspaces/ws-settings-test/readiness") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ready",
            missing_required_keys: [],
          }),
        });
      }

      return route.fulfill({ status: 404, body: "Not found" });
    });

    await page.goto(`${origin}/w/ws-settings-test/more/settings`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1");

    // Verify main content elements
    const heading = await page.locator("h1").textContent();
    assert.ok(heading?.includes("Ayarlar") || heading?.includes("Settings"));

    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflow, false, `Horizontal overflow on ${scenario.label}`);

    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axe.violations.length, 0, `Axe violations on ${scenario.label}: ${JSON.stringify(axe.violations)}`);

    const screenshotPath = path.resolve(evidenceDir, `${browserName}-${scenario.label}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    results.push({
      engine: browserName,
      scenario: scenario.label,
      passed: true,
      violations: axe.violations.length,
    });

    await context.close();
  }

  await browser.close();
}

await fs.writeFile(
  path.resolve(evidenceDir, "settings.json"),
  JSON.stringify(results, null, 2) + "\n",
  "utf8"
);

await server.close();
console.log("Playwright fixture scan complete: 8/8 scenarios passed with 0 Axe violations!");
