// Session 06 production fixture checks: Today dashboard and Commands.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s06/", import.meta.url));
await mkdir(output, { recursive: true });

const server = await preview({ preview: { port: 5186, host: "127.0.0.1" } });
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

const staffMe = {
  user: { id: "88888888-8888-4888-8888-888888888888", display_name: "Mehmet Demir", email: "mehmet@example.test", ui_locale: "en" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "staff", is_demo: false }],
};

const mockReport = {
  local_date: "2026-11-01",
  timezone: "Europe/Istanbul",
  period_start: "2026-10-31T21:00:00Z",
  period_end: "2026-11-01T14:30:00Z",
  generated_at: "2026-11-01T14:30:00Z",
  is_partial: true,
  definitions_version: "1",
  has_simulated_data: true,
  metrics: [
    { key: "inbound_messages", value: 14, link: { route: `/w/${ws}/more/reports/2026-11-01/inbound_messages` } },
    { key: "replies_sent", value: 8, link: { route: `/w/${ws}/more/reports/2026-11-01/replies_sent` } },
    { key: "attention_now", value: 2, link: { route: `/w/${ws}/inbox` } },
    { key: "pending_approvals_now", value: 3, link: { route: `/w/${ws}/approvals` } },
    { key: "content_published", value: 1, link: { route: `/w/${ws}/more/reports/2026-11-01/content_published` } },
    { key: "content_failed", value: 1, link: { route: `/w/${ws}/content?tab=problems` } },
    { key: "content_on_hold_now", value: 2, link: { route: `/w/${ws}/content?tab=problems` } },
    { key: "integration_errors", value: 0, link: { route: `/w/${ws}/more/reports/2026-11-01/integration_errors` } },
  ],
  summary: { empty: false, text: "Bugün 14 mesaj alındı, 8 yanıt gönderildi.", sections: [] },
};

const mockStaffReport = {
  ...mockReport,
  metrics: [
    { key: "inbound_messages", value: 14, link: { route: `/w/${ws}/more/reports/2026-11-01/inbound_messages` } },
    { key: "replies_sent", value: 8, link: { route: `/w/${ws}/more/reports/2026-11-01/replies_sent` } },
    { key: "attention_now", value: 2, link: { route: `/w/${ws}/inbox` } },
  ],
};

const mockReadiness = {
  level: "ready_for_drafts",
  requirements: [
    { code: "business_name", required_for: "drafts", satisfied: true, status: "ok", link: { target: "knowledge", category: "identity", key: "identity.business_name" }, missing_keys: [] },
    { code: "booking_instructions", required_for: "ready", satisfied: false, status: "missing", link: { target: "knowledge", category: "booking", key: "booking.instructions" }, missing_keys: ["booking.instructions"] },
    { code: "account_connected", required_for: "ready", satisfied: false, status: "not_connected", link: { target: "integrations", category: null, key: null }, missing_keys: [] },
  ],
};

const mockUpcoming = [
  {
    id: "c1000000-0000-4000-8000-000000000001",
    workspace_id: ws,
    title: "Pazartesi Motivasyonu",
    content_type: "feed_image",
    status: "scheduled",
    scheduled_at: "2026-11-02T08:00:00Z",
    is_simulated: true,
    media_asset_id: null,
    media_deleted: false,
    version: 1,
  },
];

const mockFailures = [
  {
    id: "c1000000-0000-4000-8000-000000000002",
    workspace_id: ws,
    title: "Hafta Sonu Kampanyası",
    content_type: "feed_image",
    status: "failed",
    last_error_code: "MEDIA_REJECTED",
    is_simulated: true,
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
        { width: 360, locale: "tr", role: "owner", label: "tr-phone-owner" },
        { width: 390, locale: "en", role: "staff", label: "en-phone-staff" },
        { width: 768, locale: "tr", role: "owner", label: "tr-tablet-owner" },
        { width: 1440, locale: "en", role: "owner", label: "en-desktop-owner" },
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

        const isOwner = scenario.role === "owner";
        const currentMe = isOwner ? ownerMe : staffMe;
        currentMe.user.ui_locale = scenario.locale;

        await context.route("**/*", async (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== origin) {
            blocked.push(url.href);
            return route.abort();
          }
          if (!url.pathname.startsWith("/api/")) return route.continue();

          const pathname = url.pathname;
          const method = route.request().method();

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
                is_demo: isOwner,
                status: "active",
                created_at: "2026-10-15T12:00:00Z",
                settings: {},
              }),
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
                    is_simulated: isOwner,
                    capabilities: { can_reply: true, can_post: true },
                  },
                ],
                next_cursor: null,
              }),
            });
          }

          if (pathname.endsWith("/reports/daily")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(isOwner ? mockReport : mockStaffReport),
            });
          }

          if (pathname.endsWith("/readiness")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(mockReadiness),
            });
          }

          if (pathname.endsWith("/content-items")) {
            if (url.searchParams.get("tab") === "scheduled") {
              return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ items: mockUpcoming, next_cursor: null }),
              });
            }
            if (url.searchParams.get("status") === "failed") {
              return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ items: mockFailures, next_cursor: null }),
              });
            }
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null }),
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

          if (["conversations", "facts", "fact-candidates", "tasks", "members", "approvals"].some((s) => pathname.endsWith(`/${s}`))) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null }),
            });
          }

          return route.fulfill({ status: 404, body: "{}" });
        });

        await page.goto(`${origin}${base}`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);

        // Verification assertions:
        const attentionSection = page.getByTestId("home-attention");
        await attentionSection.waitFor({ timeout: 5000 });
        assert.ok(await attentionSection.isVisible());

        // Overview / attention checks:
        if (isOwner) {
          const approvalsAttention = page.getByTestId("attention-pending_approvals_now");
          assert.ok(await approvalsAttention.isVisible());
          assert.ok((await approvalsAttention.getByRole("link").textContent()).includes("3"));

          const numbersInbound = page.getByTestId("number-inbound_messages");
          assert.ok(await numbersInbound.isVisible());
          assert.ok((await numbersInbound.textContent()).includes("14"));
        } else {
          // Staff should not see approvals attention
          assert.equal(await page.getByTestId("attention-pending_approvals_now").count(), 0);
          assert.ok(await page.getByTestId("attention-attention_now").isVisible());
        }

        // Upcoming content check:
        const upcomingLink = page.getByRole("link", { name: "Pazartesi Motivasyonu" });
        assert.ok(await upcomingLink.isVisible());

        // Failures check:
        const failureLink = page.getByRole("link", { name: "Hafta Sonu Kampanyası" });
        assert.ok(await failureLink.isVisible());

        // Command bar check:
        const commandInput = page.getByRole("textbox", { name: scenario.locale === "tr" ? "Komut" : "Command" });
        assert.ok(await commandInput.isVisible());

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
          role: scenario.role,
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

  await writeFile(`${output}/today.json`, JSON.stringify(results, null, 2), "utf8");
  console.log(`UI Today checks passed: ${results.length} scenarios, 0 violations, 0 overflow.`);
} finally {
  await server.close();
}
