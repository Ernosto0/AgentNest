import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s22");
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

const mockActivityItems = [
  {
    id: "act-1",
    action: "reply.sent",
    group: "replies",
    text: "Yanıt gönderildi",
    actor: { type: "user", label: "Demo Sahip" },
    occurred_at: "2026-11-01T14:30:00Z",
    is_simulated: false,
    resource: {
      type: "conversation",
      id: "c1",
      label: "ayse_k",
      link: "/w/ws-activity-test/inbox/c1",
    },
  },
  {
    id: "act-2",
    action: "content.published",
    group: "content",
    text: "Gönderi yayınlandı",
    actor: { type: "agent", label: "AgentNest" },
    occurred_at: "2026-11-01T12:00:00Z",
    is_simulated: true,
    resource: {
      type: "content_item",
      id: "cnt-1",
      label: "Haftalık Bülten",
      link: "/w/ws-activity-test/content/cnt-1",
    },
  },
  {
    id: "act-3",
    action: "fact.updated",
    group: "knowledge",
    text: "Bilgi güncellendi",
    actor: { type: "user", label: "Yönetici" },
    occurred_at: "2026-10-31T18:00:00Z",
    is_simulated: false,
    resource: {
      type: "business_fact",
      id: "f1",
      label: "Aylık üyelik",
      link: null,
    },
  },
];

const mockNotifications = [
  {
    id: "notif-1",
    type: "account.needs_reauth",
    severity: "critical",
    is_simulated: false,
    read_at: null,
    created_at: "2026-11-01T14:00:00Z",
    params: {
      social_account_id: "sa-1",
      username: "golkent.demo",
    },
  },
  {
    id: "notif-2",
    type: "approval.requested",
    severity: "attention",
    is_simulated: true,
    read_at: null,
    created_at: "2026-11-01T11:00:00Z",
    params: {
      action: "command.update_fact",
      summary: { label: "Aylık üyelik" },
    },
  },
  {
    id: "notif-3",
    type: "knowledge.fact_changed",
    severity: "info",
    is_simulated: false,
    read_at: "2026-11-01T09:00:00Z",
    created_at: "2026-11-01T08:30:00Z",
    params: {
      label: "Açılış Saati",
      old_display: "09:00",
      new_display: "08:30",
    },
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
      const method = route.request().method();

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
              is_active: true,
            },
            memberships: [
              {
                workspace_id: "ws-activity-test",
                role: scenario.role,
              },
            ],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-activity-test") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "ws-activity-test",
            name: "Gölkent Test",
            role: scenario.role,
            timezone: "Europe/Istanbul",
            currency: "TRY",
            business_kind: "sports_facility",
            market: "TR",
            is_demo: false,
            created_at: "2026-01-01T00:00:00Z",
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-activity-test/readiness") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ready",
            missing_required_keys: [],
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-activity-test/activity") {
        const typeFilter = url.searchParams.get("type");
        const filtered = typeFilter
          ? mockActivityItems.filter((i) => i.group === typeFilter)
          : mockActivityItems;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: filtered,
            next_cursor: null,
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-activity-test/notifications") {
        const unreadOnly = url.searchParams.get("unread") === "true";
        const items = unreadOnly
          ? mockNotifications.filter((n) => n.read_at === null)
          : mockNotifications;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items,
            unread_count: mockNotifications.filter((n) => n.read_at === null).length,
            next_cursor: null,
          }),
        });
      }

      if (pathName === "/api/v1/workspaces/ws-activity-test/notifications/read-all") {
        return route.fulfill({ status: 204 });
      }

      return route.fulfill({ status: 404, body: "Not found" });
    });

    // 1. Activity Feed Test (Owner & Manager see activity feed; for staff, we test notification center)
    if (scenario.role !== "staff") {
      await page.goto(`${origin}/w/ws-activity-test/more/activity`, { waitUntil: "networkidle" });
      await page.waitForSelector('[data-testid="activity-entry"]');

      const entries = await page.locator('[data-testid="activity-entry"]').count();
      assert.equal(entries, 3, "Activity entries should match mock count");

      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth + 1;
      });
      assert.equal(overflow, false, `Horizontal overflow on ${scenario.label} (activity)`);

      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .disableRules(["color-contrast"])
        .analyze();
      assert.equal(axe.violations.length, 0, `Axe violations on ${scenario.label}: ${JSON.stringify(axe.violations)}`);
    }

    // 2. Notification Center Test
    await page.goto(`${origin}/w/ws-activity-test/more/notifications`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-severity]');

    const notifCount = await page.locator('[data-severity]').count();
    assert.ok(notifCount > 0, "Notification rows should be present");

    const bellCount = await page.locator('[data-testid="notification-count"]').textContent();
    assert.equal(bellCount?.trim(), "2", "Notification bell count should reflect unread count");

    const overflowNotif = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflowNotif, false, `Horizontal overflow on ${scenario.label} (notifications)`);

    const axeNotif = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axeNotif.violations.length, 0, `Axe violations on ${scenario.label} (notifications): ${JSON.stringify(axeNotif.violations)}`);

    const screenshotPath = path.resolve(evidenceDir, `${browserName}-${scenario.label}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    results.push({
      engine: browserName,
      scenario: scenario.label,
      passed: true,
      violations: axeNotif.violations.length,
    });

    await context.close();
  }

  await browser.close();
}

await fs.writeFile(
  path.resolve(evidenceDir, "activity-notifications.json"),
  JSON.stringify(results, null, 2) + "\n",
  "utf8"
);

await server.close();
console.log("Playwright fixture scan complete: 8/8 scenarios passed with 0 Axe violations!");
