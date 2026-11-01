// Session 14 production fixture checks: Voice, delegation, controller transitions, and legacy automation settings.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s14/", import.meta.url));
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

const mockPersonality = {
  version: 2,
  goals: "Müşterilere samimi ve profesyonel destek sağla",
  personality: {
    tone: "warm",
    formality: "professional",
    length: "short",
    emoji: "sparse",
    dm_style: "conversational",
    comment_style: "concise",
    examples: { tr: ["Merhaba, size nasıl yardımcı olabilirim?"], en: ["Hello, how can I help you today?"] },
  },
};

const mockDelegation = {
  version: 1,
  config_version: 3,
  controller_epoch: 2,
  policy: {
    actions: {
      "dm.send": { mode: "ask", sources: ["customer", "owner_task"], max_per_day: 50 },
      "comment.reply": { mode: "automatic", sources: ["customer"], max_per_day: 100 },
      "comment.private_reply": { mode: "ask", sources: ["customer"], max_per_day: 20 },
      "comment.hide": { mode: "off", sources: ["customer"], max_per_day: null },
      "comment.unhide": { mode: "off", sources: ["customer"], max_per_day: null },
      "comment.delete": { mode: "off", sources: ["customer"], max_per_day: null },
      "content.prepare": { mode: "automatic", sources: ["owner_task"], max_per_day: 10 },
      "content.schedule": { mode: "ask", sources: ["owner_task"], max_per_day: 5 },
      "content.publish": { mode: "ask", sources: ["owner_task"], max_per_day: 5 },
      "content.cancel": { mode: "ask", sources: ["owner_task"], max_per_day: 5 },
    },
  },
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

const mockAutomation = {
  auto_allowed: true,
  readiness_level: "ready",
  reviewed_at: null,
  items: [
    { action_class: "reply.hours", mode: "auto" },
    { action_class: "reply.pricing", mode: "approval" },
    { action_class: "reply.location", mode: "auto" },
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
                  capabilities: { messaging: true, comment_reply: true, comment_moderate: true },
                },
              ],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent`) {
            return respond(mockOverview);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/personality`) {
            return respond(mockPersonality);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/delegation`) {
            return respond(mockDelegation);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/delegation/preview`) {
            return respond({
              next_version: 2,
              changed_actions: ["dm.send"],
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/tasks`) {
            return respond({ items: [], next_cursor: null });
          }

          if (pathname === `/api/v1/workspaces/${ws}/automation-policies`) {
            return respond(mockAutomation);
          }

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          if (pathname.endsWith("/readiness")) {
            return respond({ overall_status: "ready", requirements: [], warnings: [] });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // 1. Visit Agent Page (Voice, Delegation, Controller transitions)
        await page.goto(`${origin}${base}/more/agent?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify Voice section & sample conversation preview disclosure
        const previewVoiceBtn = scenario.locale === "tr" ? "Örnek konuşmayı önizle" : "Preview a sample conversation";
        await page.getByRole("button", { name: previewVoiceBtn }).waitFor({ state: "visible", timeout: 8000 });
        await page.getByRole("button", { name: previewVoiceBtn }).click();

        // Verify Delegation section & preview button
        const previewDelegationBtn = scenario.locale === "tr" ? "Yetki değişikliklerini önizle" : "Preview permission changes";
        await page.getByRole("button", { name: previewDelegationBtn }).waitFor({ state: "visible", timeout: 8000 });
        await page.getByRole("button", { name: previewDelegationBtn }).click();

        // Verify Version diff preview appeared
        const applyBtn = scenario.locale === "tr" ? "Bu yetkileri uygula" : "Apply these permissions";
        await page.getByRole("button", { name: applyBtn }).waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Agent Page
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on agent page in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit on Agent Page
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const agentShot = `${output}/${engine.name}-${scenario.label}-agent.png`;
        await page.screenshot({ path: agentShot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations on agent page in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Legacy Automation Settings (Route R12)
        // With mockOverview modified to legacy controller mode
        await context.route(`**/api/v1/workspaces/${ws}/accounts/${accountId}/agent`, async (route) => {
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ ...mockOverview, controller_mode: "legacy" }),
          });
        });

        await page.goto(`${origin}${base}/more/automation`, { waitUntil: "networkidle" });
        await page.waitForSelector("[data-testid='account-status']");

        // Check horizontal overflow on Legacy Automation Page
        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on automation page in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const autoShot = `${output}/${engine.name}-${scenario.label}-automation.png`;
        await page.screenshot({ path: autoShot, fullPage: true });

        assert.equal(axe.violations.length, 0, `Axe violations on automation page in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          axeAgent: 0,
          axeAutomation: 0,
          overflow: false,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(
    `${output}/voice-delegation.json`,
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2),
    "utf8"
  );
  console.log("Session 14 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}

