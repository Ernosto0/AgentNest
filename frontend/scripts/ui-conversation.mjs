// Session 08 production fixture checks: Conversation, Grounded Drafts, and Composer.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s08/", import.meta.url));
await mkdir(output, { recursive: true });

const server = await preview({ preview: { port: 5188, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const convoId = "c1000000-0000-4000-8000-000000000001";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockDetail = {
  conversation: {
    id: convoId,
    customer_handle: "Ayşe Yılmaz",
    customer_number: 1042,
    last_message_preview: "Merhaba, aylık fitness ve havuz üyelik ücretleriniz nedir?",
    last_message_at: "2026-11-01T12:00:00Z",
    attention: "needs_approval",
    handling_mode: "automatic",
    window_ends_at: new Date(Date.now() + 18 * 3_600_000).toISOString(),
    is_simulated: true,
    social_account_id: null,
  },
  messages: [
    {
      id: "m-1",
      direction: "inbound",
      sender_kind: "customer",
      text: "Merhaba, aylık fitness ve havuz üyelik ücretleriniz nedir?",
      attachments: [],
      provider_timestamp: "2026-11-01T11:58:00Z",
      is_simulated: true,
    },
    {
      id: "m-2",
      direction: "outbound",
      sender_kind: "agent",
      text: "Merhaba Ayşe Hanım! Aylık fitness üyelik ücretimiz 6.000 ₺ / ay.",
      attachments: [],
      provider_timestamp: "2026-11-01T12:00:00Z",
      is_simulated: true,
    },
  ],
  open_draft: {
    id: "d-1",
    conversation_id: convoId,
    status: "pending_approval",
    source: "ai",
    language: "tr",
    intent: "pricing",
    flags: [],
    text: "Merhaba Ayşe Hanım! Aylık fitness üyelik ücretimiz 6.000 ₺ / ay.",
    suggestion_text: null,
    rendered_facts: [
      {
        fact_id: "f-1",
        key: "pricing.membership_monthly",
        label: "Aylık üyelik",
        display: "6.000 ₺ / ay",
        version: 1,
        span: [43, 56],
      },
    ],
    validation: { passed: true, issues: [] },
    decision: "approval_required",
    decision_reasons: ["POLICY_REQUIRES_APPROVAL"],
    approval_id: "app-1",
    approval_state: null,
    version: 1,
    failure_code: null,
    window_ends_at: null,
    created_at: "2026-11-01T12:00:00Z",
    is_simulated: true,
  },
  recent_drafts: [],
};

const mockApproval = {
  id: "app-1",
  workspace_id: ws,
  action: "reply.send",
  kind: "authorization",
  status: "pending",
  can_decide: true,
  payload_hash: "mock-hash-123",
  summary: { reply_text: "Merhaba Ayşe Hanım! Aylık fitness üyelik ücretimiz 6.000 ₺ / ay." },
  expires_at: new Date(Date.now() + 10 * 3_600_000).toISOString(),
  created_at: "2026-11-01T12:00:00Z",
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

          if (pathname === `/api/v1/workspaces/${ws}/conversations/${convoId}`) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(mockDetail),
            });
          }

          if (pathname === `/api/v1/workspaces/${ws}/approvals/app-1`) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(mockApproval),
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

          if (["conversations", "social-accounts", "content-items", "facts", "fact-candidates", "tasks", "members", "approvals"].some((s) => pathname.endsWith(`/${s}`))) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null }),
            });
          }

          return route.fulfill({ status: 404, body: "{}" });
        });

        await page.goto(`${origin}${base}/inbox/${convoId}`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);

        // Verification assertions:
        const heading = page.getByRole("heading", { name: "Ayşe Yılmaz", level: 1 });
        await heading.waitFor({ timeout: 5000 });
        assert.ok(await heading.isVisible());

        // Messages stream check:
        const messagesList = page.getByTestId("messages");
        assert.ok(await messagesList.isVisible());
        assert.equal(await messagesList.getByRole("listitem").count(), 2);

        // Draft card check:
        const draftCard = page.getByTestId("draft-card");
        assert.ok(await draftCard.isVisible());

        // Grounded fact chip interaction test:
        const factChip = draftCard.getByTestId("fact-chip");
        assert.ok(await factChip.isVisible());
        await factChip.click();
        const factSource = draftCard.getByRole("status");
        assert.ok(await factSource.isVisible());
        assert.ok((await factSource.textContent()).includes("Aylık üyelik"));

        // Decision buttons check:
        const approveBtn = draftCard.getByRole("button", {
          name: scenario.locale === "tr" ? "Onayla ve gönder" : "Approve and send",
        });
        assert.ok(await approveBtn.isVisible());

        // Composer check:
        const composer = page.getByRole("textbox", {
          name: scenario.locale === "tr" ? "Yanıtınız" : "Your reply",
        });
        assert.ok(await composer.isVisible());

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

  await writeFile(`${output}/conversation.json`, JSON.stringify(results, null, 2), "utf8");
  console.log(`UI Conversation checks passed: ${results.length} scenarios, 0 violations, 0 overflow.`);
} finally {
  await server.close();
}

