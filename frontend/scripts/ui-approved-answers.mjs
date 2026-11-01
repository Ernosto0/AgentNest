import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s20");
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

const mockAnswers = [
  {
    id: "ans-01",
    title: "Aylık üyelik ve fiyatlandırma",
    intent: "pricing",
    language: "tr",
    status: "active",
    example_questions: ["Aylık üyelik ne kadar?", "Fiyat bilgisi alabilir miyim?"],
    answer_template: "Aylık spor salonu üyeliğimiz {{fact:pricing.membership_monthly}}'dir. Detaylı bilgi ve kayıt için bekleriz!",
    created_from_message_id: null,
    version: 1,
    updated_at: "2026-10-25T12:00:00Z",
  },
  {
    id: "ans-02",
    title: "Opening Hours Inquiry",
    intent: "hours",
    language: "en",
    status: "needs_review",
    example_questions: ["What time do you open?", "Weekend hours?"],
    answer_template: "Our gym is open {{fact:hours.weekly}}. Stop by anytime during staff hours!",
    created_from_message_id: "msg-ext-456",
    version: 2,
    updated_at: "2026-10-26T14:00:00Z",
  },
];

const engines = [
  { name: "chromium", launcher: chromium },
  { name: "webkit", launcher: webkit },
];

const ws = "ws-ans-test";
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

          if (pathname.endsWith("/approved-answers")) {
            return respond({ items: mockAnswers, next_cursor: null });
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // 1. Visit Approved Answers Library (Route R22, Control K19)
        await page.goto(`${origin}${base}/more/knowledge/answers`, { waitUntil: "networkidle" });

        // Verify title
        const pageTitle = scenario.locale === "tr" ? "Onaylı yanıtlar" : "Approved answers";
        await page.getByRole("heading", { name: pageTitle }).waitFor({ state: "visible", timeout: 8000 });

        // Verify answers are rendered
        await page.getByText("Aylık üyelik ve fiyatlandırma").waitFor({ state: "visible", timeout: 5000 });

        // Check horizontal overflow
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on approved answers in ${engine.name} ${scenario.label}`);

        // Run Axe accessibility audit
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        assert.equal(axe.violations.length, 0, `Axe violations on approved answers in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

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
    path.join(evidenceDir, "approved-answers.json"),
    JSON.stringify(auditResults, null, 2),
    "utf8",
  );

  console.log("Session 20 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
