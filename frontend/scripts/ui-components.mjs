// Session03 fixture-only browser evidence. No database, auth, or external service.
// Run a Vite dev server on5186 first (or set UI_REFERENCE_ORIGIN to localhost).
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const origin = process.env.UI_REFERENCE_ORIGIN ?? "http://127.0.0.1:5186";
assert.ok(["localhost", "127.0.0.1"].includes(new URL(origin).hostname));
const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s03/", import.meta.url));
await mkdir(output, { recursive: true });
const results = [];
for (const engine of [{ name: "chromium", type: chromium }, { name: "webkit", type: webkit }]) {
  const browser = await engine.type.launch();
  try {
    for (const scenario of [{ locale: "tr", width: 360 }, { locale: "en", width: 1440 }]) {
      const context = await browser.newContext({ viewport: { width: scenario.width, height: 900 }, locale: scenario.locale, timezoneId: "Europe/Istanbul", serviceWorkers: "block" });
      const page = await context.newPage();
      const requests = [];
      const errors = [];
      const blocked = [];
      page.on("pageerror", error => errors.push(error.message));
      await context.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin || url.pathname.startsWith("/api/")) { blocked.push(url.href); return route.abort(); }
        requests.push(url.pathname);
        return route.continue();
      });
      await page.goto(`${origin}/?ui-reference=1&lang=${scenario.locale}`, { waitUntil: "networkidle" });
      const reference = page.getByTestId("shared-reference");
      await reference.waitFor();
      await page.evaluate(() => document.fonts.ready);
      const initialScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      assert.deepEqual(initialScan.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) })), [], "Shared specimen accessibility scan");
      const save = reference.getByRole("button", { name: scenario.locale === "tr" ? "Örneği kaydet" : "Save example", exact: true });
      await save.click();
      const summary = reference.getByRole("alert").filter({ hasText: scenario.locale === "tr" ? "Örnek hataları" : "Review the example errors" });
      await summary.getByRole("link").click();
      const name = page.locator("#reference-name");
      assert.equal(await name.evaluate(element => element === document.activeElement), true);
      await name.fill("İstanbul Example");
      await save.click();
      assert.equal(await name.inputValue(), "İstanbul Example");
      const nextLabel = scenario.locale === "tr" ? "Sonraki" : "Next";
      await reference.getByRole("button", { name: nextLabel, exact: true }).click();
      assert.match(await reference.locator("li").textContent(), /2/);
      await page.getByTestId("open-sheet").scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${output}/${engine.name}-${scenario.locale}-${scenario.width}-controls.png`, fullPage: true });
      const trigger = page.getByTestId("open-sheet");
      await trigger.click();
      const dialog = page.getByRole("dialog");
      await dialog.waitFor();
      const initialFocus = await dialog.locator("input").evaluate(element => element === document.activeElement);
      assert.equal(initialFocus, true);
      assert.equal(await page.locator("#root").getAttribute("inert"), "");
      const closeLabel = scenario.locale === "tr" ? "Kapat" : "Close";
      const doneLabel = scenario.locale === "tr" ? "İncelemeyi bitir" : "Finish review";
      await dialog.getByRole("button", { name: doneLabel }).focus();
      await page.keyboard.press("Tab");
      assert.equal(await dialog.getByRole("button", { name: closeLabel, exact: true }).evaluate(element => element === document.activeElement), true);
      await page.keyboard.press("Shift+Tab");
      assert.equal(await dialog.getByRole("button", { name: doneLabel }).evaluate(element => element === document.activeElement), true);
      const modalScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      assert.deepEqual(modalScan.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) })), [], "Modal accessibility scan");
      const modalBounds = await dialog.boundingBox();
      assert.ok(modalBounds.y >= 0 && modalBounds.y + modalBounds.height <= 901);
      await page.screenshot({ path: `${output}/${engine.name}-${scenario.locale}-${scenario.width}-sheet.png`, fullPage: false });
      const nestedTrigger = dialog.getByRole("button", { name: scenario.locale === "tr" ? "İç paneli aç" : "Open nested sheet" });
      await nestedTrigger.click();
      await page.keyboard.press("Escape");
      assert.equal(await page.getByRole("dialog").count(), 1);
      assert.equal(await nestedTrigger.evaluate(element => element === document.activeElement), true);
      await page.getByTestId("prior-focus-sheet").click();
      await page.keyboard.press("Escape");
      assert.equal(await dialog.locator("input").evaluate(element => element === document.activeElement), true);
      await page.keyboard.press("Escape");
      assert.equal(await page.getByRole("dialog").count(), 0);
      assert.equal(await trigger.evaluate(element => element === document.activeElement), true);
      assert.equal(await page.locator("#root").getAttribute("inert"), null);
      const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      assert.equal(layout.width, layout.scrollWidth);
      // CSS zoom/reflow is a reproducible stress probe, not actual device/browser zoom acceptance.
      await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
      const zoom = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
      assert.ok(zoom.scrollWidth <= zoom.width, `CSS200% overflow ${JSON.stringify(zoom)}`);
      await page.evaluate(() => { document.documentElement.style.zoom = ""; });
      assert.deepEqual(errors, []);
      assert.deepEqual(blocked, []);
      results.push({ browser: engine.name, version: browser.version(), ...scenario, height: 900, timezone: "Europe/Istanbul", initialAxeViolations: initialScan.violations.length, modalAxeViolations: modalScan.violations.length, initialFocus, modalBounds, layout, cssZoom200: zoom, requests: requests.length, apiRequests: 0, externalRequests: 0, pageErrors: errors, keyboard: "initial focus; Tab/Shift+Tab trap; nested Escape with explicit opener return; default return to prior input; parent Escape with explicit opener return", validation: "summary link focuses invalid field; save retains entered value", pagination: "caller-controlled next advances row" });
      await context.close();
    }
  } finally { await browser.close(); }
}
await writeFile(`${output}/components.json`, `${JSON.stringify({ executedAt: new Date().toISOString(), platform: process.platform, node: process.version, scenarios: results }, null, 2)}\n`);
console.log(`Verified ${results.length} shared-control scenarios; evidence: ${output}`);
