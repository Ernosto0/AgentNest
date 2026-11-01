// Session 07 production fixture checks: Inbox List and Desktop Workspace.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s07/", import.meta.url));
await mkdir(output, { recursive: true });

const server = await preview({ preview: { port: 5187, host: "127.0.0.1" } });
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

const mockConversations = [
  {
    id: "c1000000-0000-4000-8000-000000000001",
    customer_handle: "Ayşe Yılmaz",
    customer_number: 1042,
    last_message_preview: "Merhaba, aylık fitness ve havuz üyelik ücretleriniz nedir?",
    last_message_at: "2026-11-01T12:00:00Z",
    attention: "needs_approval",
    handling_mode: "automatic",
    window_ends_at: new Date(Date.now() + 18 * 3_600_000).toISOString(),
    is_simulated: true,
  },
  {
    id: "c1000000-0000-4000-8000-000000000002",
    customer_handle: null,
    customer_number: 4821,
    last_message_preview: "Dünkü antrenman seansım iptal oldu, iade talebini nasıl oluşturabilirim?",
    last_message_at: "2026-11-01T11:15:00Z",
    attention: "needs_human",
    handling_mode: "human",
    window_ends_at: new Date(Date.now() + 10 * 3_600_000).toISOString(),
    is_simulated: true,
  },
  {
    id: "c1000000-0000-4000-8000-000000000003",
    customer_handle: "Çok Uzun Müşteri Adı İle Test Edilen Özel Instagram Kullanıcısı",
    customer_number: 9912,
    last_message_preview: "Çalışma saatleriniz hafta sonu kaça kadar açık acaba?",
    last_message_at: "2026-11-01T09:30:00Z",
    attention: "none",
    handling_mode: "automatic",
    window_ends_at: new Date(Date.now() + 5 * 3_600_000).toISOString(),
    is_simulated: false,
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

          if (pathname.endsWith("/conversations")) {
            const attention = url.searchParams.get("attention");
            let items = mockConversations;
            if (attention && attention !== "any") {
              items = mockConversations.filter((c) => c.attention === attention);
            }
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items, next_cursor: null }),
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

          if (["social-accounts", "content-items", "facts", "fact-candidates", "tasks", "members", "approvals"].some((s) => pathname.endsWith(`/${s}`))) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null }),
            });
          }

          return route.fulfill({ status: 404, body: "{}" });
        });

        await page.goto(`${origin}${base}/inbox`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);

        // Verification assertions:
        const firstConvo = page.getByRole("link", { name: /Ayşe Yılmaz/ });
        await firstConvo.waitFor({ timeout: 5000 });
        assert.ok(await firstConvo.isVisible());

        // Attention chip check:
        const attentionChip = page.getByTestId("attention-chip").first();
        assert.ok(await attentionChip.isVisible());

        // Window timer check:
        const windowTimer = page.getByTestId("window-timer").first();
        assert.ok(await windowTimer.isVisible());

        // Simulation badge check:
        assert.ok((await page.getByTestId("simulated-badge").count()) > 0);

        // Filter tab switching check:
        const filterTabs = page.getByRole("tablist", { name: scenario.locale === "tr" ? "Konuşmaları filtrele" : "Filter conversations" });
        assert.ok(await filterTabs.isVisible());

        // Long name check:
        const longNameLink = page.getByText("Çok Uzun Müşteri Adı İle Test Edilen Özel Instagram Kullanıcısı");
        assert.ok(await longNameLink.isVisible());

        // Desktop layout check (at >= 1024px width, placeholder selection prompt is visible):
        if (scenario.width >= 1024) {
          const selectHeading = page.getByRole("heading", {
            name: scenario.locale === "tr" ? "Bir konuşma seçin" : "Select a conversation",
          });
          assert.ok(await selectHeading.isVisible());
        }

        // Axe accessibility scan:
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

  await writeFile(`${output}/inbox.json`, JSON.stringify(results, null, 2), "utf8");
  console.log(`UI Inbox checks passed: ${results.length} scenarios, 0 violations, 0 overflow.`);
} finally {
  await server.close();
}

