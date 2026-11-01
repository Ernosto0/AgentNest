// Session 13 production fixture checks: Agent overview, account selector, tasks, and task detail clarification.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s13/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const accountId = "sa-agent-1";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockOverview = {
  state: "active",
  controller_mode: "agent",
  config_version: 3,
  controller_epoch: 2,
  is_simulated: true,
  session_counts: { waiting_owner: 1, running: 2 },
  pending_questions: 1,
  pending_approvals: 2,
  recent_actions: [
    { id: "act-1", action_type: "dm.send", status: "outcome_unknown", operation_id: "op-1", created_at: "2026-10-31T12:00:00Z" },
  ],
};

const mockTask = {
  id: "task-1",
  account_id: accountId,
  status: "waiting_owner",
  clarification: "Hangi kampanya görseli kullanılsın?",
  question_version: 2,
  actions: [
    {
      action_id: "act-sch",
      action_type: "content.schedule",
      status: "succeeded",
      content_id: "c-1",
      content_status: "scheduled",
      is_simulated: true,
    },
  ],
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
        page.on("pageerror", (err) => errors.push(err.message));
        page.on("console", (msg) => {
          if (msg.type() === "error") console.error("PAGE LOG:", msg.text());
        });

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
                  capabilities: { messaging: true, comment_reply: true },
                },
              ],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent`) {
            return respond(mockOverview);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/personality`) {
            return respond({
              version: 2,
              goals: "Müşterilere yardım et",
              personality: {
                tone: "warm",
                formality: "professional",
                length: "short",
                emoji: "moderate",
                dm_style: "conversational",
                comment_style: "concise",
                examples: { tr: [], en: [] },
              },
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/delegation`) {
            return respond(null);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/tasks`) {
            return respond({
              items: [mockTask],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/tasks/task-1`) {
            return respond(mockTask);
          }

          if (pathname.endsWith("/task-selections")) {
            return respond({ items: [{ id: "m-1", label: "Afiş Görseli" }], next_cursor: null });
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          if (pathname.endsWith("/readiness")) {
            return respond({ overall_status: "ready", requirements: [], warnings: [] });
          }

          console.warn("404 unhandled:", pathname);
          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // 1. Visit Agent Overview
        await page.goto(`${origin}${base}/more/agent?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify overview cards and task items
        const taskHeading = scenario.locale === "tr" ? "İstekleriniz" : "Your requests";
        await page.getByRole("heading", { name: taskHeading }).waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on overview in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit on Overview
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const shot = `${output}/${engine.name}-${scenario.label}-overview.png`;
        await page.screenshot({ path: shot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Task Detail with Clarification
        await page.goto(`${origin}${base}/more/agent/tasks/task-1?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("textarea");

        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on task detail in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const taskShot = `${output}/${engine.name}-${scenario.label}-task.png`;
        await page.screenshot({ path: taskShot, fullPage: true });

        assert.equal(axe.violations.length, 0, `Axe violations on task detail in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          violations: axe.violations.length,
          errors: errors.length,
          overflow: overflow.hasOverflow,
          shot,
          taskShot,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(`${output}/agent-tasks.json`, JSON.stringify(results, null, 2), "utf8");
  console.log("Session 13 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
