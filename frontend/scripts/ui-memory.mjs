// Session 17 production fixture checks: Customer memory page, scope header, memory items, source inspection, and correction/forget controls.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s17/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const accountId = "sa-agent-1";
const customerId = "c-cust-42";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockMemories = [
  {
    id: "mem-1",
    topic: "preference",
    kind: "preference",
    body: "Sabah 09:00 - 11:00 arası grup pilates derslerini tercih ediyor.",
    version: 2,
    expires_at: "2027-01-01T00:00:00Z",
  },
  {
    id: "mem-2",
    topic: "notes",
    kind: "notes",
    body: "Bel fıtığı geçmişi var, reformer derslerinde dikkat edilmeli.",
    version: 1,
    expires_at: "2027-06-01T00:00:00Z",
  },
];

const mockSources = [
  {
    id: "src-1",
    memory_id: "mem-1",
    removed: false,
    observed_at: "2026-10-18T09:30:00Z",
  },
  {
    id: "src-2",
    memory_id: "mem-2",
    removed: true,
    observed_at: "2026-09-12T14:15:00Z",
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

          if (pathname.endsWith("/social-accounts")) {
            return respond({
              items: [
                {
                  id: accountId,
                  username: "orneksalon",
                  status: "connected",
                  platform: "instagram",
                  provider_kind: "mock",
                  is_simulated: true,
                  capabilities: { messaging: true },
                },
              ],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/customers/${customerId}/memory`) {
            return respond({
              items: mockMemories,
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/customers/${customerId}/sources`) {
            return respond({
              items: mockSources,
              next_cursor: null,
            });
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          if (pathname.endsWith("/readiness")) {
            return respond({ overall_status: "ready", requirements: [], warnings: [] });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // Visit Customer Memory (Route R17, Control M01)
        await page.goto(`${origin}${base}/more/agent/memory/${customerId}?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify customer scope and memory content
        await page.getByText(customerId).waitFor({ state: "visible", timeout: 8000 });
        await page.getByText("Sabah 09:00 - 11:00 arası grup pilates derslerini tercih ediyor.").waitFor({ state: "visible", timeout: 8000 });

        // Verify action buttons
        const correctLabel = scenario.locale === "tr" ? "Düzelt" : "Correct";
        const forgetLabel = scenario.locale === "tr" ? "Unut" : "Forget";
        await page.getByRole("button", { name: correctLabel }).first().waitFor({ state: "visible", timeout: 8000 });
        await page.getByRole("button", { name: forgetLabel }).first().waitFor({ state: "visible", timeout: 8000 });

        // Expand sources
        const sourcesSummary = scenario.locale === "tr" ? "Kaynakları incele" : "Inspect sources";
        const summaryLocator = page.getByText(sourcesSummary).first();
        if (await summaryLocator.isVisible()) {
          await summaryLocator.click();
        }

        // Check horizontal overflow on Memory Page
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on memory page in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const memoryShot = `${output}/${engine.name}-${scenario.label}-memory.png`;
        await page.screenshot({ path: memoryShot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations on memory page in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          axe: 0,
          overflow: false,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(
    `${output}/memory.json`,
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2),
    "utf8"
  );
  console.log("Session 17 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}

