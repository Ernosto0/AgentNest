// Session 09 production fixture checks: Content library, thumbnails, and GenerateSheet.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s09/", import.meta.url));
await mkdir(output, { recursive: true });

const server = await preview({ preview: { port: 5189, host: "127.0.0.1" } });
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

const mockDrafts = [
  {
    id: "c-draft-1",
    workspace_id: ws,
    title: "Pazartesi Motivasyon Postu",
    content_type: "feed_image",
    status: "draft",
    updated_at: "2026-11-01T10:00:00Z",
    is_simulated: true,
    media_asset_id: null,
    media_deleted: false,
    version: 1,
  },
  {
    id: "c-draft-2",
    workspace_id: ws,
    title: "Haftalık Havuz Saatleri Duyurusu",
    content_type: "story_image",
    status: "pending_approval",
    updated_at: "2026-11-01T09:30:00Z",
    is_simulated: false,
    media_asset_id: null,
    media_deleted: false,
    version: 1,
  },
];

const mockScheduled = [
  {
    id: "c-sched-1",
    workspace_id: ws,
    title: "Yeni Sezon İndirimi",
    content_type: "feed_image",
    status: "scheduled",
    scheduled_at: "2026-11-02T14:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
    is_simulated: true,
    media_asset_id: null,
    media_deleted: false,
    version: 2,
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

          if (pathname === "/api/v1/meta") {
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

          if (pathname === "/api/v1/auth/me") {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(currentMe),
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}`) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                id: ws,
                name: name,
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
              }),
            });
          }

          if (pathname.endsWith("/content-items")) {
            const tab = url.searchParams.get("tab");
            let items = mockDrafts;
            if (tab === "scheduled") items = mockScheduled;
            else if (tab === "published" || tab === "problems") items = [];
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items, next_cursor: null }),
            });
          }

          if (pathname.endsWith("/social-accounts")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
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
              }),
            });
          }

          if (pathname.endsWith("/notifications")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], unread_count: 0, next_cursor: null }),
            });
          }

          if (pathname.endsWith("/facts/template")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify([]),
            });
          }

          if (["conversations", "facts", "fact-candidates", "tasks", "members", "approvals"].some((s) => pathname.endsWith(`/${s}`))) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null }),
            });
          }

          return route.fulfill({ status: 404, body: "{}" });
        });

        await page.goto(`${origin}${base}/content`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);

        // Verification assertions:
        const firstCard = page.getByRole("link", { name: /Pazartesi Motivasyon Postu/ });
        await firstCard.waitFor({ timeout: 5000 });
        assert.ok(await firstCard.isVisible());

        // Tabs check:
        const tabList = page.getByRole("tablist", { name: scenario.locale === "tr" ? "İçerik listesi" : "Content list" });
        assert.ok(await tabList.isVisible());

        // Actions check:
        const newDraftBtn = page.getByRole("button", {
          name: scenario.locale === "tr" ? "Taslak iste" : "Ask for a draft",
        });
        assert.ok(await newDraftBtn.isVisible());

        const blankDraftBtn = page.getByRole("button", {
          name: scenario.locale === "tr" ? "Boş taslak" : "Blank draft",
        });
        assert.ok(await blankDraftBtn.isVisible());

        // Interactive sheet open test:
        await newDraftBtn.click();
        const sheetDialog = page.getByRole("dialog");
        await sheetDialog.waitFor({ timeout: 5000 });
        assert.ok(await sheetDialog.isVisible());

        // Axe accessibility scan on open sheet:
        const scan = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        assert.deepEqual(
          scan.violations.map((v) => ({ id: v.id, help: v.help })),
          [],
          `Axe violations in ${engine.name} ${scenario.label}: ${JSON.stringify(scan.violations)}`
        );

        // Overflow check:
        const overflow = await page.evaluate(() => ({
          viewport: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        assert.equal(
          overflow.scrollWidth,
          overflow.viewport,
          `Horizontal overflow in ${engine.name} ${scenario.label}: ${overflow.scrollWidth} > ${overflow.viewport}`
        );

        // Save screenshot:
        const screenshotPath = `${output}/${engine.name}-${scenario.label}.png`;
        await page.screenshot({ path: screenshotPath, fullPage: true });

        // Close sheet:
        await page.keyboard.press("Escape");

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          width: scenario.width,
          locale: scenario.locale,
          errors,
          blocked,
          violations: scan.violations.length,
          overflow: overflow.scrollWidth - overflow.viewport,
          screenshot: `${engine.name}-${scenario.label}.png`,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(`${output}/content.json`, JSON.stringify(results, null, 2), "utf8");
  console.log(`UI Content checks passed: ${results.length} scenarios, 0 violations, 0 overflow.`);
} finally {
  await server.close();
}
