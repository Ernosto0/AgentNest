// Fixture-only visual baseline. Never starts an API, database, worker, or E2E global setup.
// Run after `npm run build` and `npm run preview -- --host 127.0.0.1 --port 5185`.
import { chromium } from "@playwright/test";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { resolve, sep } from "node:path";

const origin = process.env.UI_BASELINE_ORIGIN ?? "http://127.0.0.1:5185";
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname)) throw new Error("Local origin required");
const output = process.env.UI_BASELINE_OUTPUT
  ? `${resolve(process.env.UI_BASELINE_OUTPUT)}${sep}`
  : fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s01/", import.meta.url));
await mkdir(output, { recursive: true });
const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const report = { local_date: "2026-10-30", timezone: "Europe/Istanbul", period_start: "2026-10-29T21:00:00Z", period_end: "2026-10-30T09:00:00Z", generated_at: "2026-10-30T09:00:00Z", is_partial: true, definitions_version: "1", has_simulated_data: true, metrics: [], summary: { empty: true, text: "", sections: [] } };
const workspace = { id: ws, name: "Örnek Atölye / Example Studio", slug: "example-studio", business_category: "fitness", market: "tr", default_locale: "tr", reply_languages: ["tr"], timezone: "Europe/Istanbul", currency: "TRY", is_demo: true, status: "active", created_at: "2026-10-15T12:00:00Z", settings: { automation_reviewed_at: null, disclosure_enabled: true, disclosure_text: { tr: "", en: "" }, daily_report_hour: 20, publish_max_delay_minutes: 1440 } };
const metrics = [];
const browser = await chromium.launch();
try {
  for (const scenario of [
    { id: "login-tr-phone", path: "/login", locale: "tr", width: 390, signedIn: false },
    { id: "login-en-desktop", path: "/login", locale: "en", width: 1440, signedIn: false },
    { id: "today-tr-desktop", path: base, locale: "tr", width: 1440, signedIn: true },
    { id: "today-en-phone", path: base, locale: "en", width: 390, signedIn: true },
    { id: "more-staff-tr-phone", path: `${base}/more`, locale: "tr", width: 360, signedIn: true, role: "staff" },
    { id: "picker-en-desktop", path: "/", locale: "en", width: 1440, signedIn: true },
  ]) {
    const context = await browser.newContext({ viewport: { width: scenario.width, height: 900 }, locale: scenario.locale, timezoneId: "Europe/Istanbul", serviceWorkers: "block" });
    const page = await context.newPage();
    const apiRequests = [];
    const blocked = [];
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await context.route("**/*", async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) { blocked.push(url.origin); return route.abort(); }
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (route.request().method() !== "GET") throw new Error("Baseline fixture allows GET requests only");
      const pathname = url.pathname;
      let status = 200;
      let data;
      if (pathname === "/api/v1/meta") data = { product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", mock_requires_demo_workspace: true };
      else if (pathname === "/api/v1/auth/me") {
        if (!scenario.signedIn) { status = 401; data = { code: "AUTH_REQUIRED", status: 401, params: {} }; }
        else data = { user: { id: "99999999-9999-4999-8999-999999999999", email: "owner@example.test", display_name: "Örnek Kullanıcı", ui_locale: scenario.locale }, csrf_token: "fictional-fixture-csrf", memberships: [{ workspace_id: ws, workspace_name: workspace.name, role: scenario.role ?? "owner", is_demo: true }] };
      } else if (pathname === `/api/v1/workspaces/${ws}`) data = workspace;
      else if (pathname.endsWith("/notifications")) data = { items: [], unread_count: 0, next_cursor: null };
      else if (pathname.endsWith("/social-accounts") || pathname.endsWith("/content-items")) data = { items: [], next_cursor: null };
      else if (pathname.endsWith("/reports/daily")) data = report;
      else if (pathname.endsWith("/readiness")) data = { level: "not_ready", requirements: [{ code: "account_connected", required_for: "ready", satisfied: false, status: "not_connected", link: { target: "integrations", category: null, key: null }, missing_keys: [] }] };
      else throw new Error(`Unmocked baseline API: ${pathname}`);
      const body = JSON.stringify(data);
      apiRequests.push({ method: route.request().method(), path: `${pathname}${url.search}`, status, bytes: Buffer.byteLength(body) });
      return route.fulfill({ status, contentType: "application/json", body });
    });
    const start = performance.now();
    await page.goto(`${origin}${scenario.path}`, { waitUntil: "networkidle" });
    await page.locator("h1").waitFor();
    const settledMs = Math.round(performance.now() - start);
    await page.screenshot({ path: `${output}${scenario.id}.png`, fullPage: true });
    const measured = await page.evaluate(() => ({ title: document.querySelector("h1")?.textContent, scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth, font: getComputedStyle(document.body).fontFamily, resources: performance.getEntriesByType("resource").map(entry => ({ name: new URL(entry.name).pathname, encodedBytes: entry.encodedBodySize, decodedBytes: entry.decodedBodySize, durationMs: Math.round(entry.duration) })), cls: null }));
    let subsequent = null;
    if (scenario.path === base) {
      const count = apiRequests.length;
      const nextStart = performance.now();
      await page.locator(`a[href="${base}/more"]:visible`).click();
      await page.waitForURL(`${origin}${base}/more`);
      await page.getByRole("heading", { level: 1, name: scenario.locale === "tr" ? "Daha fazla" : "More", exact: true }).waitFor();
      subsequent = { path: `${base}/more`, settledMs: Math.round(performance.now() - nextStart), addedApiRequests: apiRequests.length - count };
    }
    metrics.push({ ...scenario, browser: browser.version(), settledMs, ...measured, apiRequests, blockedExternalOrigins: blocked, errors, subsequent });
    await context.close();
  }
  const assetDir = fileURLToPath(new URL("../dist/assets/", import.meta.url));
  const assets = [];
  for (const name of await readdir(assetDir)) { const bytes = await readFile(`${assetDir}/${name}`); assets.push({ name, bytes: bytes.length, gzipBytes: gzipSync(bytes).length }); }
  await writeFile(`${output}baseline.json`, `${JSON.stringify({ fixtureOnly: true, origin, node: process.version, platform: process.platform, assets, scenarios: metrics }, null, 2)}\n`);
} finally { await browser.close(); }
console.log(`Baseline captured in ${output}`);
