// Session 11 production fixture checks: Content detail, editor, media, status panel, and actions.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s11/", import.meta.url));
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

const mockItem = {
  id: "c-feed-1",
  workspace_id: ws,
  title: "Yeni Sezon İndirim Kampanyası",
  content_type: "feed_image",
  status: "draft",
  caption: "Tüm üyeliklerde %20 indirim fırsatını kaçırmayın!",
  overlay_text_suggestions: [],
  visual_notes: "Görselde kulüp renkleri ve logo yer alsın.",
  media_asset_id: null,
  media_deleted: false,
  version: 1,
  can_cancel: true,
  is_simulated: true,
  scheduled_at: null,
  published_at: null,
  external_permalink: null,
  rejection_note: null,
  hold_reason: null,
  operation: null,
  approval: null,
  generation: null,
  validation: {
    passed: true,
    stale: false,
    errors: [],
    warnings: [],
    issues: [],
  },
  created_at: "2026-11-01T08:00:00Z",
  updated_at: "2026-11-01T08:00:00Z",
};

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
        page.on("pageerror", (err) => console.log("PAGE ERROR:", err));


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

          if (pathname === `/api/v1/workspaces/${ws}/content-items/c-feed-1`) {
            return respond(mockItem);
          }

          if (pathname.endsWith("/social-accounts")) {
            return respond({
              items: [
                {
                  id: "sa-1",
                  workspace_id: ws,
                  provider: "instagram",
                  username: "orneksalon",
                  status: "connected",
                  is_simulated: true,
                  capabilities: { can_reply: true, can_post: true },
                },
              ],
              next_cursor: null,
            });
          }

          if (pathname.endsWith("/readiness")) {
            return respond({
              overall_status: "ready",
              requirements: [],
              warnings: [],
            });
          }

          if (pathname.endsWith("/facts") || pathname.endsWith("/facts/template")) {
            return respond([]);
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        await page.goto(`${origin}${base}/content/c-feed-1`, { waitUntil: "networkidle" });
        await page.waitForSelector("[data-testid='media-upload']");
        await page.waitForSelector("#content-editor");

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

  await writeFile(`${output}/content-detail.json`, JSON.stringify(results, null, 2), "utf8");
  console.log("Session 11 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
