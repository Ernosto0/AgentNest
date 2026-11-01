import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s21");
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

const mockReport = {
  local_date: "2026-11-01",
  timezone: "Europe/Istanbul",
  period_start: "2026-10-31T21:00:00Z",
  period_end: "2026-11-01T15:30:00Z",
  generated_at: "2026-11-01T15:30:00Z",
  is_partial: true,
  evidence_complete: true,
  has_simulated_data: false,
  definitions_version: "1",
  summary: {
    empty: false,
    text: "Günün özeti",
    sections: [
      {
        section: "inbox",
        title: "Gelen kutusu ve mesajlar",
      },
      {
        section: "content",
        title: "İçerik ve paylaşımlar",
      },
    ],
  },
  metrics: [
    {
      key: "conversations_inbound",
      section: "inbox",
      value: 14,
      link: { route: "/w/ws-report-test/more/reports/2026-11-01/conversations_inbound" },
      screen_link: { route: "/w/ws-report-test/inbox" },
    },
    {
      key: "replies_sent",
      section: "inbox",
      value: 12,
      link: { route: "/w/ws-report-test/more/reports/2026-11-01/replies_sent" },
      screen_link: { route: "/w/ws-report-test/inbox" },
    },
    {
      key: "median_first_response_minutes",
      section: "inbox",
      value: 4.5,
      link: { route: "/w/ws-report-test/more/reports/2026-11-01/median_first_response_minutes" },
      screen_link: null,
    },
    {
      key: "posts_published",
      section: "content",
      value: 2,
      link: { route: "/w/ws-report-test/more/reports/2026-11-01/posts_published" },
      screen_link: { route: "/w/ws-report-test/content" },
    },
  ],
};

const mockMetricItems = {
  items: [
    {
      id: "item-01",
      kind: "conversation",
      label: "@fitness_lover ile sohbet",
      occurred_at: "2026-11-01T10:15:00Z",
      measure: null,
      is_simulated: false,
      link: { route: "/w/ws-report-test/inbox/conv-1" },
    },
    {
      id: "item-02",
      kind: "conversation",
      label: "@sporcu_ali ile sohbet",
      occurred_at: "2026-11-01T11:45:00Z",
      measure: null,
      is_simulated: false,
      link: { route: "/w/ws-report-test/inbox/conv-2" },
    },
  ],
  value: 14,
  snapshot_id: "snap-123",
  next_cursor: null,
};

const engines = [
  { name: "chromium", launcher: chromium },
  { name: "webkit", launcher: webkit },
];

const ws = "ws-report-test";
const name = "Ornek Salon";
const base = `/w/${ws}`;

const auditResults = [];

try {
  for (const engine of engines) {
    const browser = await engine.launcher.launch({ headless: true });

    for (const scenario of scenarios) {
      const context = await browser.newContext({
        viewport: scenario.viewport,
        locale: scenario.locale === "tr" ? "tr-TR" : "en-US",
      });

      const page = await context.newPage();

      try {
        await page.addInitScript(
          ({ lang }) => {
            localStorage.setItem("agentnest.locale", lang);
            localStorage.setItem("i18nextLng", lang);
          },
          { lang: scenario.locale },
        );

        const currentMe = {
          user: {
            id: `u-${scenario.role}`,
            email: `${scenario.role}@agentnest.example`,
            display_name: `${scenario.role.toUpperCase()} User`,
            ui_locale: scenario.locale,
          },
          csrf_token: "fixture-csrf-token",
          memberships: [
            {
              workspace_id: ws,
              workspace_name: name,
              workspace_slug: "ornek-salon",
              role: scenario.role,
              is_active: true,
            },
          ],
        };

        await page.route("**/*", async (route) => {
          const url = new URL(route.request().url());
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

          if (pathname.includes("/metrics/")) {
            return respond(mockMetricItems);
          }

          if (pathname.includes("/reports/daily")) {
            return respond(mockReport);
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // 1. Visit Daily Report (Route R23, Control E01)
        await page.goto(`${origin}${base}/more/reports`, { waitUntil: "networkidle" });

        // Verify title
        const reportTitle = scenario.locale === "tr" ? "Günlük rapor" : "Daily report";
        await page.getByRole("heading", { name: reportTitle }).waitFor({ state: "visible", timeout: 8000 });

        // Verify date controls and metrics
        await page.getByTestId("report-day").waitFor({ state: "visible", timeout: 5000 });
        await page.getByTestId("report-as-of").waitFor({ state: "visible", timeout: 5000 });

        // Check horizontal overflow on Report overview
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on daily report in ${engine.name} ${scenario.label}`);

        // Run Axe accessibility audit on Daily Report
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        assert.equal(axe.violations.length, 0, `Axe violations on daily report in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Metric Drilldown Items (Route R24, Control E02)
        await page.goto(`${origin}${base}/more/reports/2026-11-01/conversations_inbound`, { waitUntil: "networkidle" });

        // Verify drilldown title and count
        await page.getByTestId("metric-count").waitFor({ state: "visible", timeout: 8000 });
        await page.getByText("@fitness_lover").first().waitFor({ state: "visible", timeout: 5000 });

        // Check horizontal overflow on Metric Items
        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on metric items in ${engine.name} ${scenario.label}`);

        // Run Axe accessibility audit on Metric Items
        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        assert.equal(axe.violations.length, 0, `Axe violations on metric items in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // Screenshot for evidence
        const shotPath = path.join(evidenceDir, `${engine.name}-${scenario.label}.png`);
        await page.screenshot({ path: shotPath, fullPage: true });

        auditResults.push({
          engine: engine.name,
          scenario: scenario.label,
          passed: true,
          violations: 0,
        });
      } finally {
        await context.close();
      }
    }

    await browser.close();
  }

  await fs.writeFile(
    path.join(evidenceDir, "reports.json"),
    JSON.stringify(auditResults, null, 2),
    "utf8",
  );

  console.log("Session 21 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
