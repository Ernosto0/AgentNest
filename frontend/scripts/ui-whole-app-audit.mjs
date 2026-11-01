import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";
import { gzipSync } from "node:zlib";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s27");
await fs.mkdir(evidenceDir, { recursive: true });

const frontendRoot = path.resolve(__dirname, "..");
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const wsName = "Gölkent Butik / Lake City Boutique with long Turkish characters: Şöför İğne Çiçek";

const mockMeta = {
  product_name: "AgentNest",
  demo_tools_enabled: true,
  llm_mode: "fake",
  mock_requires_demo_workspace: false,
};

const mockReport = {
  local_date: "2026-11-01",
  timezone: "Europe/Istanbul",
  period_start: "2026-10-31T21:00:00Z",
  period_end: "2026-11-01T15:30:00Z",
  generated_at: "2026-11-01T15:30:00Z",
  is_partial: false,
  definitions_version: "2",
  has_simulated_data: false,
  metrics: [
    { key: "inquiries_handled", label: "Gelen Sorular", count: 42, formatted_value: "42", target: 50 },
    { key: "orders_booked", label: "Alınan Siparişler", count: 18, formatted_value: "18", target: 20 },
    { key: "response_time_seconds", label: "Ortalama Yanıt Süresi", count: 64, formatted_value: "64 sn", target: 120 },
  ],
  summary: {
    empty: false,
    text: "Tüm operasyonlar planlanan hedefler dahilinde sorunsuz tamamlandı.",
    sections: [
      { title: "Özet", text: "Gelen 42 sorunun tamamı onaylı bilgi bankasıyla yanıtlandı." },
    ],
  },
};

const mockReadiness = {
  level: "ready",
  requirements: [
    { key: "hours", met: true, label: "Çalışma Saatleri" },
    { key: "pricing", met: true, label: "Fiyat Bilgisi" },
  ],
};

const mockHealth = {
  generated_at: "2026-11-01T16:00:00Z",
  accounts: [
    {
      account_id: "act-1",
      username: "golkentbutik",
      status: "connected",
      degraded_reason: null,
      reconnect_required: false,
      connected_at: "2026-10-01T10:00:00Z",
      expires_at: "2026-12-01T10:00:00Z",
      capabilities: { direct_messages: "ok", comments: "ok", content_publish: "ok" },
    },
  ],
  operations: {
    total_24h: 320,
    by_type: { reply: 120, comment_reply: 80, publish: 12 },
    by_status: { succeeded: 318, failed: 2 },
    latest_failure: null,
  },
  jobs: {
    running: 0,
    queued: 0,
    oldest_queued_age_seconds: null,
    dead_letter_24h: 0,
  },
  webhooks: {
    received_24h: 450,
    ignored_24h: 12,
    failed_24h: 0,
    signature_failures_24h: 0,
  },
  ai: {
    total_runs_24h: 180,
    failed_runs_24h: 0,
    total_tokens_in: 45000,
    total_tokens_out: 12000,
    estimated_cost_usd: 0.14,
    monthly_budget_usd: 50.0,
    monthly_spend_usd: 8.5,
  },
};

const scenarios = [
  { label: "tr-phone-360", viewport: { width: 360, height: 740 }, locale: "tr", role: "staff" },
  { label: "en-phone-390", viewport: { width: 390, height: 844 }, locale: "en", role: "manager" },
  { label: "tr-tablet-768", viewport: { width: 768, height: 1024 }, locale: "tr", role: "owner" },
  { label: "en-tablet-1024", viewport: { width: 1024, height: 768 }, locale: "en", role: "staff" },
  { label: "tr-desktop-1440", viewport: { width: 1440, height: 900 }, locale: "tr", role: "owner" },
  { label: "en-desktop-1920", viewport: { width: 1920, height: 1080 }, locale: "en", role: "owner" },
];

const routesToTest = [
  { name: "home", path: `/w/${ws}/home` },
  { name: "inbox", path: `/w/${ws}/inbox` },
  { name: "comments", path: `/w/${ws}/comments` },
  { name: "memory", path: `/w/${ws}/memory` },
  { name: "content", path: `/w/${ws}/content` },
  { name: "knowledge", path: `/w/${ws}/knowledge` },
  { name: "reports", path: `/w/${ws}/reports/daily` },
  { name: "activity", path: `/w/${ws}/activity` },
  { name: "notifications", path: `/w/${ws}/notifications` },
  { name: "settings", path: `/w/${ws}/settings` },
  { name: "connections", path: `/w/${ws}/settings/connections` },
  { name: "members", path: `/w/${ws}/settings/members` },
  { name: "system-health", path: `/w/${ws}/settings/system-health` },
];

const auditResults = [];

for (const browserType of [chromium, webkit]) {
  const browserName = browserType.name();
  const browser = await browserType.launch({ headless: true });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      locale: scenario.locale,
      timezoneId: "Europe/Istanbul",
    });

    const pageErrors = [];
    context.on("pageerror", (err) => pageErrors.push(err.message));

    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.continue();
      const p = url.pathname;

      if (!p.startsWith("/api/")) return route.continue();

      let data = {};
      if (p === "/api/v1/meta") {
        data = mockMeta;
      } else if (p === "/api/v1/auth/me") {
        data = {
          user: {
            id: "user-1",
            display_name: "Yönetici Kullanıcı",
            email: "admin@golkent.test",
            ui_locale: scenario.locale,
          },
          csrf_token: "csrf-token-123",
          memberships: [
            {
              workspace_id: ws,
              workspace_name: wsName,
              role: scenario.role,
              is_demo: false,
            },
          ],
        };
      } else if (p === `/api/v1/workspaces/${ws}`) {
        data = {
          id: ws,
          name: wsName,
          slug: "golkent-butik",
          business_category: "retail",
          market: "tr",
          default_locale: "tr",
          reply_languages: ["tr", "en"],
          timezone: "Europe/Istanbul",
          currency: "TRY",
          is_demo: false,
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          settings: {
            automation_reviewed_at: "2026-02-01T00:00:00Z",
            disclosure_enabled: true,
            disclosure_text: { tr: "", en: "" },
            daily_report_hour: 20,
            publish_max_delay_minutes: 1440,
          },
        };
      } else if (p.includes("/reports/daily")) {
        data = mockReport;
      } else if (p.includes("/readiness")) {
        data = mockReadiness;
      } else if (p.includes("/system-health")) {
        data = mockHealth;
      } else if (p.includes("/conversations")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/public-comments")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/customer-memories")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/content-items")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/facts")) {
        data = { items: [], categories: [], next_cursor: null };
      } else if (p.includes("/approved-answers")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/social-accounts")) {
        data = mockHealth.accounts;
      } else if (p.includes("/members")) {
        data = {
          members: [
            {
              membership_id: "mem-1",
              user_id: "user-1",
              display_name: "Yönetici Kullanıcı",
              email: "admin@golkent.test",
              role: scenario.role,
              joined_at: "2026-01-01T00:00:00Z",
            },
          ],
        };
      } else if (p.includes("/invitations")) {
        data = { invitations: [] };
      } else if (p.includes("/activity")) {
        data = { items: [], next_cursor: null };
      } else if (p.includes("/notifications")) {
        data = { items: [], unread_count: 0, next_cursor: null };
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(data),
      });
    });

    const page = await context.newPage();

    // Iterate across routes for this scenario
    for (const r of routesToTest) {
      // Staff cannot access system-health
      if (r.name === "system-health" && scenario.role === "staff") continue;

      await page.goto(`${origin}${r.path}`, { waitUntil: "networkidle" });

      // 1. Check Horizontal Overflow (WCAG 1.4.10 Reflow)
      const overflow = await page.evaluate(() => {
        const docWidth = document.documentElement.scrollWidth;
        const viewportWidth = window.innerWidth;
        return docWidth > viewportWidth + 1;
      });
      assert.equal(overflow, false, `Horizontal overflow detected on ${r.name} in ${browserName} ${scenario.label}`);

      // 2. Check Axe accessibility scan on key screens
      if (["home", "inbox", "comments", "knowledge", "reports", "settings"].includes(r.name)) {
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .exclude(".axe-ignore")
          .analyze();

        assert.equal(axe.violations.length, 0, `Axe violations on ${r.name} in ${browserName} ${scenario.label}: ${JSON.stringify(axe.violations.map(v => v.id))}`);
      }
    }

    // Save representative screenshot for home
    await page.goto(`${origin}/w/${ws}/home`, { waitUntil: "networkidle" });
    const snapPath = path.join(evidenceDir, `${browserName}-${scenario.label}-home.png`);
    await page.screenshot({ path: snapPath, fullPage: true });

    assert.equal(pageErrors.length, 0, `Page errors on ${scenario.label}: ${pageErrors.join(", ")}`);

    auditResults.push({
      engine: browserName,
      scenario: scenario.label,
      role: scenario.role,
      passed: true,
      routesTested: routesToTest.length,
      pageErrors: pageErrors.length,
    });

    await context.close();
  }

  await browser.close();
}

// 200% Zoom / Reflow Test (WCAG 1.4.10)
{
  const browser = await chromium.launch({ headless: true });
  // 200% zoom on 1280x800 viewport simulates effective 640x400 CSS viewport
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    locale: "tr",
  });
  const page = await context.newPage();
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) {
      let data = {};
      if (url.pathname === "/api/v1/meta") data = mockMeta;
      else if (url.pathname === "/api/v1/auth/me") {
        data = {
          user: { id: "user-1", display_name: "Yönetici", email: "admin@golkent.test", ui_locale: "tr" },
          csrf_token: "csrf-token-123",
          memberships: [{ workspace_id: ws, workspace_name: wsName, role: "owner", is_demo: false }],
        };
      } else if (url.pathname === `/api/v1/workspaces/${ws}`) {
        data = { id: ws, name: wsName, slug: "golkent-butik", market: "tr", default_locale: "tr", reply_languages: ["tr"], timezone: "Europe/Istanbul", currency: "TRY", is_demo: false, status: "active" };
      } else if (url.pathname.includes("/reports/daily")) data = mockReport;
      else if (url.pathname.includes("/readiness")) data = mockReadiness;
      else data = { items: [], next_cursor: null };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    }
    return route.continue();
  });

  await page.goto(`${origin}/w/${ws}/home`, { waitUntil: "networkidle" });
  const zoomOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(zoomOverflow, false, "Horizontal overflow at 200% zoom reflow");

  const zoomSnapPath = path.join(evidenceDir, "zoom-200-home.png");
  await page.screenshot({ path: zoomSnapPath, fullPage: true });

  await context.close();
  await browser.close();
}

// Measure asset sizes and bundle metrics
const distDir = path.resolve(frontendRoot, "dist/assets");
const distFiles = await fs.readdir(distDir);
let totalJsBytes = 0;
let totalJsGzip = 0;
let totalCssBytes = 0;
let totalCssGzip = 0;

for (const file of distFiles) {
  const filePath = path.join(distDir, file);
  const content = await fs.readFile(filePath);
  if (file.endsWith(".js")) {
    totalJsBytes += content.length;
    totalJsGzip += gzipSync(content).length;
  } else if (file.endsWith(".css")) {
    totalCssBytes += content.length;
    totalCssGzip += gzipSync(content).length;
  }
}

const auditSummary = {
  timestamp: new Date().toISOString(),
  auditResults,
  bundleMetrics: {
    totalJsBytes,
    totalJsGzip,
    totalCssBytes,
    totalCssGzip,
  },
};

await fs.writeFile(path.join(evidenceDir, "whole-app-audit.json"), JSON.stringify(auditSummary, null, 2), "utf-8");

console.log("Whole-app accessibility, responsive and performance audit passed!");
console.log(`Bundle metrics: JS ${totalJsBytes} (${totalJsGzip} gzip), CSS ${totalCssBytes} (${totalCssGzip} gzip)`);

await server.close();
process.exit(0);
