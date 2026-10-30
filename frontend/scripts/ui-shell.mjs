// Session04 production fixture checks. Does not start/reset a database or call real APIs.
import assert from "node:assert/strict";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const origin = process.env.UI_SHELL_ORIGIN ?? "http://127.0.0.1:5185";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(origin).hostname));
const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s04/", import.meta.url));
await mkdir(output, { recursive: true });
const ws = "11111111-1111-4111-8111-111111111111";
const nextWs = "22222222-2222-4222-8222-222222222222";
const base = `/w/${ws}`;
const name = "Örnek Atölye / Example Studio with a long workspace name";
const report = { local_date: "2026-10-30", timezone: "Europe/Istanbul", period_start: "2026-10-29T21:00:00Z", period_end: "2026-10-30T09:00:00Z", generated_at: "2026-10-30T09:00:00Z", is_partial: true, definitions_version: "1", has_simulated_data: true, metrics: [], summary: { empty: true, text: "", sections: [] } };
const findings = [];
for (const engine of [{ name: "chromium", type: chromium }, { name: "webkit", type: webkit }]) {
  const browser = await engine.type.launch();
  try {
    for (const scenario of [
      { width: 360, locale: "tr", role: "staff" },
      { width: 390, locale: "en", role: "manager" },
      { width: 768, locale: "tr", role: "owner" },
      { width: 1024, locale: "en", role: "staff" },
      { width: 1440, locale: "tr", role: "owner" },
      { width: 1920, locale: "en", role: "manager" },
    ]) {
      const context = await browser.newContext({ viewport: { width: scenario.width, height: 900 }, locale: scenario.locale, timezoneId: "Europe/Istanbul", serviceWorkers: "block" });
      const page = await context.newPage();
      const requests = [], blocked = [], errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await context.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) { blocked.push(url.href); return route.abort(); }
        if (!url.pathname.startsWith("/api/")) return route.continue();
        assert.equal(route.request().method(), "GET", "Shell fixture permits read-only APIs");
        const pathname = url.pathname;
        let data;
        if (pathname === "/api/v1/meta") data = { product_name: "AgentNest", demo_tools_enabled: false, llm_mode: "fake", mock_requires_demo_workspace: true };
        else if (pathname === "/api/v1/auth/me") data = { user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Example Owner", email: "owner@example.test", ui_locale: scenario.locale }, csrf_token: "fictional-fixture-csrf", memberships: [{ workspace_id: ws, workspace_name: name, role: scenario.role, is_demo: true }, { workspace_id: nextWs, workspace_name: "Second example studio", role: scenario.role, is_demo: true }] };
        else if (pathname === `/api/v1/workspaces/${ws}` || pathname === `/api/v1/workspaces/${nextWs}`) data = { id: pathname.endsWith(nextWs) ? nextWs : ws, name: pathname.endsWith(nextWs) ? "Second example studio" : name, slug: "example-studio", business_category: "fitness", market: "tr", default_locale: "tr", reply_languages: ["tr"], timezone: "Europe/Istanbul", currency: "TRY", is_demo: true, status: "active", created_at: "2026-10-15T12:00:00Z", settings: { automation_reviewed_at: null, disclosure_enabled: true, disclosure_text: { tr: "", en: "" }, daily_report_hour: 20, publish_max_delay_minutes: 1440 } };
        else if (pathname.endsWith("/notifications")) data = { items: [], unread_count: 12, next_cursor: null };
        else if (pathname.endsWith("/reports/daily")) data = report;
        else if (pathname.endsWith("/facts/template")) data = [];
        else if (pathname.endsWith("/readiness")) data = { level: "not_ready", requirements: [] };
        else if (["social-accounts", "content-items", "conversations", "facts", "fact-candidates"].some(suffix => pathname.endsWith(`/${suffix}`))) data = { items: [], next_cursor: null };
        else throw new Error(`Unmocked shell API ${pathname}`);
        const body = JSON.stringify(data);
        requests.push({ method: route.request().method(), path: `${pathname}${url.search}`, bytes: Buffer.byteLength(body) });
        return route.fulfill({ status: 200, contentType: "application/json", body });
      });
      const started = performance.now();
      await page.goto(`${origin}${base}/more?custom=preserved`, { waitUntil: "networkidle" });
      await page.getByRole("heading", { level: 1, name: scenario.locale === "tr" ? "Daha fazla" : "More", exact: true }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      const settledMs = Math.round(performance.now() - started);
      const initialRequests = requests.length;
      const sidebar = page.getByTestId("desktop-sidebar");
      const visibleNav = page.getByRole("navigation", { name: scenario.locale === "tr" ? "Ana gezinme" : "Main navigation" });
      assert.equal(await visibleNav.count(), 1);
      assert.equal(await visibleNav.getByRole("link", { name: scenario.locale === "tr" ? "Bugün" : "Today", exact: true }).count(), 1);
      if (scenario.width < 768) assert.equal(await visibleNav.getByRole("link").count(), 5);
      else {
        assert.equal((await sidebar.boundingBox()).width, scenario.width >= 1200 ? 240 : 96);
        assert.equal(await visibleNav.getByRole("link", { name: scenario.locale === "tr" ? "Asistan" : "Assistant", exact: true }).count(), 1);
      }
      const main = page.getByRole("main");
      assert.equal(await main.getByRole("link", { name: scenario.locale === "tr" ? "Etkinlik" : "Activity", exact: true }).count(), scenario.role === "staff" ? 0 : 1);
      assert.equal(await main.getByRole("link", { name: scenario.locale === "tr" ? "Geliştirici araçları" : "Developer tools", exact: true }).count(), 0);
      assert.equal(await page.getByTestId("notification-count").textContent(), "9+");
      const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      assert.deepEqual(scan.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) })), []);
      const size = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, main: document.querySelector("main").getBoundingClientRect().width }));
      assert.equal(size.viewport, size.document);
      const id = `${engine.name}-${scenario.locale}-${scenario.width}-${scenario.role}`;
      await page.screenshot({ path: `${output}/${id}-more.png` });
      const trigger = page.getByRole("button", { name: scenario.locale === "tr" ? "Gezinme hedeflerini aç" : "Open navigation destinations" });
      await trigger.click();
      const input = page.getByRole("textbox", { name: scenario.locale === "tr" ? "Hedefleri filtrele" : "Filter destinations" });
      assert.equal(await input.evaluate(element => element === document.activeElement), true);
      await input.fill(scenario.locale === "tr" ? "İŞLETME" : "BUSINESS");
      assert.equal(await page.getByRole("dialog").getByRole("link").count(), 1);
      const modalScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      assert.deepEqual(modalScan.violations.map(item => item.id), []);
      await page.screenshot({ path: `${output}/${id}-launcher.png` });
      await page.keyboard.press("Escape");
      assert.equal(await trigger.evaluate(element => element === document.activeElement), true, "Pointer opener focus return");
      const switcher = page.getByRole("combobox", { name: scenario.locale === "tr" ? "Çalışma alanı" : "Workspace", exact: true });
      await switcher.focus();
      await page.keyboard.press("Control+k");
      await page.getByRole("dialog").waitFor();
      await page.keyboard.press("Escape");
      assert.equal(await switcher.evaluate(element => element === document.activeElement), true, "Shortcut returns prior field focus");
      if (scenario.width >= 768 && scenario.width < 1200) {
        await page.getByRole("button", { name: scenario.locale === "tr" ? "Gezinme etiketlerini aç" : "Expand navigation labels" }).click();
        assert.equal((await sidebar.boundingBox()).width, 240);
      }
      await page.goto(`${origin}${base}/inbox?attention=needs_human&account=old-account&snapshot=old-snapshot&custom=preserved`, { waitUntil: "networkidle" });
      const preservedQuery = new URL(page.url()).search;
      assert.equal(preservedQuery, "?attention=needs_human&account=old-account&snapshot=old-snapshot&custom=preserved");
      await page.reload({ waitUntil: "networkidle" });
      assert.equal(new URL(page.url()).search, preservedQuery);
      await page.getByRole("combobox", { name: scenario.locale === "tr" ? "Çalışma alanı" : "Workspace", exact: true }).selectOption(nextWs);
      await page.waitForURL(`${origin}/w/${nextWs}/inbox?attention=needs_human`);
      await page.goBack({ waitUntil: "networkidle" });
      assert.equal(new URL(page.url()).search, preservedQuery);
      assert.equal(new URL(page.url()).pathname, `${base}/inbox`);
      await page.goForward({ waitUntil: "networkidle" });
      assert.equal(new URL(page.url()).pathname, `/w/${nextWs}/inbox`);
      assert.equal(new URL(page.url()).search, "?attention=needs_human");
      assert.deepEqual(errors, []);
      assert.deepEqual(blocked, []);
      findings.push({ ...scenario, engine: engine.name, browser: browser.version(), settledMs, initialRequests, size, axeViolations: scan.violations.length, modalViolations: modalScan.violations.length, pointerFocusReturned: true, shortcutFocusReturned: true, refreshBackForwardPreserved: true, workspaceSwitchSafe: true, requests, errors, blocked });
      console.log(`${id} passed`);
      await context.close();
    }
  } finally { await browser.close(); }
}
const assets = [];
const assetDirectory = fileURLToPath(new URL("../dist/assets/", import.meta.url));
for (const name of await readdir(assetDirectory)) { const content = await readFile(`${assetDirectory}/${name}`); assets.push({ name, bytes: content.length, gzipBytes: gzipSync(content).length }); }
await writeFile(`${output}/shell.json`, `${JSON.stringify({ fixtureOnly: true, origin, node: process.version, platform: process.platform, assets, findings }, null, 2)}\n`);
console.log(`Session04: ${findings.length} production fixture browser scenarios passed`);
