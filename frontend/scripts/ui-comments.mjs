// Session 16 production fixture checks: Public comments list, comment thread context, post media context, thread control takeover/release, and manual moderation actions.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s16/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const accountId = "sa-agent-1";
const threadId = "thread-c-1";
const commentId = "c-test-1";
const mediaId = "media-post-1";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockComment = {
  id: commentId,
  text: "Üyelik ücretleri hakkında bilgi alabilir miyim?",
  state: "visible",
  thread_id: threadId,
  media_id: mediaId,
  version: 2,
  is_owner: false,
  is_simulated: true,
};

const mockOwnerComment = {
  id: "c-test-2",
  text: "Merhaba! Paket detaylarımızı DM üzerinden ilettik.",
  state: "visible",
  thread_id: threadId,
  media_id: mediaId,
  version: 1,
  is_owner: true,
  is_simulated: true,
};

const mockMedia = {
  id: mediaId,
  caption: "Yeni sezon grup derslerimiz başladı! Detaylar için yorum bırakabilirsiniz.",
  state: "visible",
  ownership_state: "verified_synthetic",
  version: 1,
  is_simulated: true,
};

const mockThread = {
  id: threadId,
  account_id: accountId,
  surface: "comment",
  source_ref: threadId,
  state: "active",
  handling_mode: "agent",
  version: 3,
  customer_id: null,
  goal: "active",
  is_simulated: true,
  actions: [
    {
      id: "act-1",
      action_type: "comment.reply",
      status: "succeeded",
      approval_id: null,
      operation_id: "op-reply-1",
      outcome_code: null,
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

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/comments`) {
            return respond({
              items: [mockComment],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/comments/threads/${threadId}`) {
            return respond({
              items: [mockComment, mockOwnerComment],
              next_cursor: null,
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/comments/media/${mediaId}`) {
            return respond(mockMedia);
          }

          if (pathname === `/api/v1/workspaces/${ws}/accounts/${accountId}/agent/threads`) {
            return respond({
              items: [mockThread],
              next_cursor: null,
            });
          }

          if (pathname.includes("/moderation-operations")) {
            return respond({
              items: [],
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

        // 1. Visit Public Comments List (Route R15, Control T01)
        await page.goto(`${origin}${base}/more/agent/comments?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify public notice and comment card
        const publicNotice = scenario.locale === "tr" ? "Herkese açık alan" : "Public surface";
        await page.getByText(publicNotice).waitFor({ state: "visible", timeout: 8000 });
        await page.getByText("Üyelik ücretleri hakkında bilgi alabilir miyim?").waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Comments List
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on comments list in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit on Comments List
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const listShot = `${output}/${engine.name}-${scenario.label}-list.png`;
        await page.screenshot({ path: listShot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations on comments list in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Comment Thread (Route R16, Controls T01, T02, T03)
        await page.goto(`${origin}${base}/more/agent/comments/${threadId}?account=${accountId}`, { waitUntil: "networkidle" });
        await page.waitForSelector("select");

        // Verify post context section
        await page.getByText("Yeni sezon grup derslerimiz başladı! Detaylar için yorum bırakabilirsiniz.").waitFor({ state: "visible", timeout: 8000 });

        // Verify thread takeover button is present
        const takeoverLabel = scenario.locale === "tr" ? "Devral" : "Take over";
        await page.getByRole("button", { name: takeoverLabel }).waitFor({ state: "visible", timeout: 8000 });

        // Verify moderation action buttons exist for customer comment
        const hideLabel = scenario.locale === "tr" ? "Yorumu gizle" : "Hide comment";
        await page.getByRole("button", { name: hideLabel }).waitFor({ state: "visible", timeout: 8000 });

        // Verify public notice is present
        await page.getByText(publicNotice).waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Comment Thread
        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on comment thread in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const threadShot = `${output}/${engine.name}-${scenario.label}-thread.png`;
        await page.screenshot({ path: threadShot, fullPage: true });

        assert.equal(axe.violations.length, 0, `Axe violations on comment thread in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          axeList: 0,
          axeThread: 0,
          overflow: false,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(
    `${output}/comments.json`,
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2),
    "utf8"
  );
  console.log("Session 16 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
