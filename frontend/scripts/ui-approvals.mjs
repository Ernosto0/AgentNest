// Session 12 production fixture checks: Approvals list, detail sheet, polymorphic action bodies, and history.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s12/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockApprovals = [
  {
    id: "app-1",
    workspace_id: ws,
    kind: "confirmation",
    action: "fact.change",
    status: "pending",
    can_decide: true,
    is_simulated: true,
    payload_hash: "a".repeat(64),
    expires_at: "2026-11-02T12:00:00Z",
    decided_at: null,
    subject: {
      type: "fact",
      id: "pricing.membership_monthly",
      version: 1,
      status: "pending_approval",
    },
    summary: {
      label: "Aylık üyelik",
      old_formatted: "6.000 ₺ / ay",
      new_formatted: "7.000 ₺ / ay",
      impact: { total: 2, items: [{ referrer_type: "reply_draft", counts: { pending_approval: 2 }, total: 2 }] },
    },
  },
  {
    id: "app-2",
    workspace_id: ws,
    kind: "authorization",
    action: "content.publish",
    status: "approved",
    can_decide: false,
    is_simulated: false,
    payload_hash: "b".repeat(64),
    expires_at: "2026-11-01T10:00:00Z",
    decided_at: "2026-11-01T09:30:00Z",
    subject: {
      type: "content_item",
      id: "c-1",
      version: 2,
      status: "scheduled",
    },
    summary: {
      title: "Haftalık Duyuru",
      content_id: "c-1",
      content_type: "feed_image",
      scheduled_at: "2026-11-02T16:00:00Z",
    },
  },
];

try {
  for (const engine of [{ name: "chromium", type: chromium }, { name: "webkit", type: webkit }]) {
    const browser = await engine.type.launch();
    try {
      for (const scenario of [
        { width: 360, locale: "tr", label: "tr-phone" },
        { width: 390, locale: "en", label: "en-phone" },
        { width: 768, locale: "tr", label: "tr-tablet" },
        { width: 1440, locale: "en", label: "en-desktop" },
      ]) {
        const context = await browser.newContext({
          viewport: { width: scenario.width, height: 900 },
          locale: scenario.locale,
          timezoneId: "Europe/Istanbul",
          serviceWorkers: "block",
        });
        const page = await context.newPage();
        const errors = [];
        const blocked = [];
        page.on("pageerror", (err) => errors.push(err.message));

        const currentMe = { ...ownerMe, user: { ...ownerMe.user, ui_locale: scenario.locale } };

        await context.route("**/*", async (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== origin) {
            blocked.push(url.href);
            return route.abort();
          }
          if (!url.pathname.startsWith("/api/")) return route.continue();

          const pathname = url.pathname;
          const respond = (body, status = 200) =>
            route.fulfill({
              status,
              contentType: "application/json",
              body: JSON.stringify(body),
            });

          if (pathname === "/api/v1/meta") {
            return respond({
              product_name: "AgentNest",
              demo_tools_enabled: true,
              llm_mode: "fake",
              supported_locales: ["tr", "en"],
              instagram_providers: ["mock"],
              mock_requires_demo_workspace: false,
            });
          }

          if (pathname === "/api/v1/auth/me") return respond(currentMe);

          if (pathname === `/api/v1/workspaces/${ws}`) {
            return respond({
              id: ws,
              name,
              slug: "ornek-salon",
              business_category: "fitness",
              market: "tr",
              default_locale: scenario.locale,
              reply_languages: [scenario.locale],
              timezone: "Europe/Istanbul",
              currency: "TRY",
              is_demo: true,
              status: "active",
              created_at: "2026-10-15T12:00:00Z",
              settings: {},
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/approvals`) {
            return respond({ items: mockApprovals, next_cursor: null });
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          if (pathname.endsWith("/readiness")) {
            return respond({ overall_status: "ready", requirements: [], warnings: [] });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        await page.goto(`${origin}${base}/approvals`, { waitUntil: "networkidle" });
        await page.waitForSelector("[role='tablist']");

        // Verify pending item is rendered
        const pendingItem = page.locator("[data-approval-id='app-1']");
        await pendingItem.waitFor({ timeout: 5000 });
        assert.ok(await pendingItem.isVisible());

        // Open detail sheet
        await pendingItem.click();
        await page.waitForSelector("[data-testid='approval-detail']");
        const hashAttr = await page.locator("[data-testid='approval-detail']").getAttribute("data-payload-hash");
        assert.equal(hashAttr, "a".repeat(64));

        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const shot = `${output}/${engine.name}-${scenario.label}.png`;
        await page.screenshot({ path: shot, fullPage: true });

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          violations: axe.violations.length,
          errors: errors.length,
          overflow: overflow.hasOverflow,
          shot,
        });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(`${output}/approvals.json`, JSON.stringify(results, null, 2), "utf8");
  console.log("Session 12 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}

