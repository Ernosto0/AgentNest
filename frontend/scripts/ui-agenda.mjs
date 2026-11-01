// Session 10 production fixture checks: Agenda view and scheduled timeline.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s10/", import.meta.url));
await mkdir(output, { recursive: true });

const server = await preview({ preview: { port: 5190, host: "127.0.0.1" } });
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
];

const mockScheduled = [
  {
    id: "c-sched-1",
    workspace_id: ws,
    title: "Pazartesi Sabah Antrenmanı",
    content_type: "feed_image",
    status: "scheduled",
    scheduled_at: "2026-11-02T06:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
    is_simulated: true,
    media_asset_id: null,
    media_deleted: false,
    version: 2,
  },
  {
    id: "c-sched-2",
    workspace_id: ws,
    title: "Çarşamba Yoga Atölyesi",
    content_type: "story_image",
    status: "scheduled",
    scheduled_at: "2026-11-04T15:30:00Z",
    updated_at: "2026-11-01T08:30:00Z",
    is_simulated: false,
    media_asset_id: null,
    media_deleted: false,
    version: 1,
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

          if (pathname.endsWith("/readiness")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                overall_status: "ready",
                requirements: [],
                warnings: [],
              }),
            });
          }

          return route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({ code: "NOT_FOUND", message: "Not found" }),
          });
        });

        // 1. Visit /content?view=agenda
        await page.goto(`${origin}${base}/content?view=agenda`, { waitUntil: "networkidle" });
        await page.waitForSelector("[data-testid='agenda-view']");

        // Verify scheduled items are rendered
        const firstPost = await page.getByText("Pazartesi Sabah Antrenmanı").isVisible();
        const secondPost = await page.getByText("Çarşamba Yoga Atölyesi").isVisible();
        assert.ok(firstPost, "First scheduled post should be visible");
        assert.ok(secondPost, "Second scheduled post should be visible");

        // Verify honesty notice and timezone
        const noticeExpected = scenario.locale === "tr" ? "Yalnızca zamanlanmış gönderiler listelenir." : "Only scheduled posts are listed.";
        const noticeVisible = await page.getByText(noticeExpected).isVisible();
        assert.ok(noticeVisible, `Notice '${noticeExpected}' should be visible`);
        const tzVisible = await page.getByText("Europe/Istanbul").isVisible();
        assert.ok(tzVisible, "Timezone Europe/Istanbul should be visible");

        // Verify view switcher tabs
        const libraryTab = page.getByRole("tab", { name: scenario.locale === "tr" ? "Kütüphane" : "Library" });
        const agendaTab = page.getByRole("tab", { name: scenario.locale === "tr" ? "Ajanda" : "Agenda" });
        assert.ok(await libraryTab.isVisible(), "Library tab should be visible");
        assert.ok(await agendaTab.isVisible(), "Agenda tab should be visible");
        assert.equal(await agendaTab.getAttribute("aria-selected"), "true");

        // 2. Check no horizontal overflow
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.ok(!overflow.hasOverflow, `Page should not horizontally overflow: ${JSON.stringify(overflow)}`);

        // 3. Run Axe accessibility audit
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        assert.equal(axe.violations.length, 0, `Axe accessibility violations: ${JSON.stringify(axe.violations, null, 2)}`);

        // 4. Capture screenshot
        const screenshotPath = `${output}/agenda-${engine.name}-${scenario.label}-${scenario.width}.png`;
        await page.screenshot({ path: screenshotPath, fullPage: true });

        // 5. Test switching back to library
        await libraryTab.click();
        await page.waitForSelector("[data-testid='agenda-view']", { state: "detached" });
        await page.waitForSelector("text=Pazartesi Motivasyon Postu");
        const draftTitleVisible = await page.getByText("Pazartesi Motivasyon Postu").isVisible();
        assert.ok(draftTitleVisible, "Draft title should be visible after switching to library");

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          width: scenario.width,
          locale: scenario.locale,
          axe_violations: axe.violations.length,
          errors: errors.length,
          blocked_requests: blocked.length,
          overflow: overflow.hasOverflow,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(`${output}/agenda.json`, JSON.stringify(results, null, 2), "utf8");
  console.log("All Agenda view checks passed successfully across 8 scenarios!");
} finally {
  await server.close();
}
