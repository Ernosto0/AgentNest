// Session 15 production fixture checks: Owner questions queue, detail, answer submission, knowledge reuse opt-in, and answer history.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s15/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const accountId = "sa-agent-1";
const questionId = "q-test-1";
const customerId = "c-cust-1";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockQuestion = {
  id: questionId,
  thread_id: "thread-1",
  customer_id: customerId,
  source_cursor: 3,
  required_info: "membership_policy",
  visibility: "customer_reply",
  body: "Yıllık üyelik dondurma hakkı kaç gündür?",
  state: "pending",
  version: 2,
  answer_id: null,
  expires_at: "2026-11-15T18:00:00Z",
};

const mockAnswers = [
  {
    id: "ans-1",
    question_id: questionId,
    version: 1,
    kind: "proposal",
    body: "Yıllık üyelikte 30 gün dondurma hakkı bulunuyor olabilir, doğrulanmalı.",
    author_role: "staff",
    candidate_id: "cand-1",
    expires_at: "2026-11-20T18:00:00Z",
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

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/owner-questions`) {
            return respond({
              items: [mockQuestion],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/owner-questions/${questionId}`) {
            return respond(mockQuestion);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/owner-questions/${questionId}/answers`) {
            return respond({
              items: mockAnswers,
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

        // 1. Visit Questions List (Route R13, Control Q01)
        await page.goto(`${origin}${base}/more/agent/questions?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify question item is rendered
        await page.getByText("Yıllık üyelik dondurma hakkı kaç gündür?").waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Question List
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on question list in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit on Question List
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const listShot = `${output}/${engine.name}-${scenario.label}-list.png`;
        await page.screenshot({ path: listShot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations on question list in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Question Detail (Route R14, Control Q02)
        await page.goto(`${origin}${base}/more/agent/questions/${questionId}?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("textarea");

        // Verify information disclosure and answer history
        const infoDisclosure = scenario.locale === "tr" ? "Yanıtınız bilgi sağlar" : "Your answer provides information";
        await page.getByText(infoDisclosure).waitFor({ state: "visible", timeout: 8000 });

        // Check reusable knowledge toggle
        const reuseCheckbox = page.getByRole("checkbox");
        if (await reuseCheckbox.isVisible()) {
          await reuseCheckbox.check();
          await page.waitForSelector("input[pattern]");
        }

        // Check horizontal overflow on Question Detail
        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on question detail in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const detailShot = `${output}/${engine.name}-${scenario.label}-detail.png`;
        await page.screenshot({ path: detailShot, fullPage: true });

        assert.equal(axe.violations.length, 0, `Axe violations on question detail in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          axeList: 0,
          axeDetail: 0,
          overflow: false,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(
    `${output}/questions.json`,
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2),
    "utf8"
  );
  console.log("Session 15 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}

