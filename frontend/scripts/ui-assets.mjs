// Fixture-only Session 02 evidence. No backend or database is contacted.
// Start Vite dev on 5186 and a production preview on 5185 before running.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { chromium } from "@playwright/test";

const devOrigin = process.env.UI_REFERENCE_ORIGIN ?? "http://127.0.0.1:5186";
const productionOrigin = process.env.UI_PRODUCTION_ORIGIN ?? "http://127.0.0.1:5185";
for (const origin of [devOrigin, productionOrigin]) {
  assert.ok(["localhost", "127.0.0.1"].includes(new URL(origin).hostname), "Local origins only");
}
const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s02/", import.meta.url));
await mkdir(output, { recursive: true });
const manifest = JSON.parse(await readFile(new URL("../public/fonts/font-manifest.json", import.meta.url), "utf8"));
for (const font of manifest) {
  const data = await readFile(new URL(`../src/assets/fonts/${font.file}`, import.meta.url));
  assert.equal(data.length, font.bytes);
  assert.equal(createHash("sha256").update(data).digest("hex"), font.sha256);
  assert.equal(data.subarray(0, 4).toString(), "wOF2");
  assert.match(await readFile(new URL(`../dist/fonts/${font.license}`, import.meta.url), "utf8"), /SIL OPEN FONT LICENSE/);
}
const browser = await chromium.launch();
const scenarios = [];
try {
  for (const scenario of [
    { id: "reference-tr-phone", origin: devOrigin, path: "/?ui-reference=1&lang=tr", width: 390, locale: "tr", reference: true },
    { id: "reference-en-desktop", origin: devOrigin, path: "/?ui-reference=1&lang=en", width: 1440, locale: "en", reference: true },
    { id: "login-tr-phone", origin: productionOrigin, path: "/login?ui-reference=1", width: 390, locale: "tr" },
    { id: "login-en-desktop", origin: productionOrigin, path: "/login?ui-reference=1", width: 1440, locale: "en" },
  ]) {
    const context = await browser.newContext({ viewport: { width: scenario.width, height: 900 }, locale: scenario.locale, timezoneId: "Europe/Istanbul", serviceWorkers: "block" });
    const page = await context.newPage();
    const blocked = [];
    const errors = [];
    const apiRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.addInitScript(() => {
      window.__fontShift = 0;
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__fontShift += entry.value;
      }).observe({ type: "layout-shift", buffered: true });
    });
    await context.route("**/*", async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== scenario.origin) { blocked.push(url.href); return route.abort(); }
      if (!url.pathname.startsWith("/api/")) return route.continue();
      assert.equal(request.method(), "GET", "No mutations allowed in asset verification");
      apiRequests.push(url.pathname);
      if (url.pathname === "/api/v1/auth/me") return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ code: "AUTH_REQUIRED", status: 401, params: {} }) });
      if (url.pathname === "/api/v1/meta") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ product_name: "AgentNest", demo_tools_enabled: true, llm_mode: "fake", supported_locales: ["tr", "en"] }) });
      throw new Error(`Unmocked asset API: ${url.pathname}`);
    });
    await page.goto(`${scenario.origin}${scenario.path}`, { waitUntil: "networkidle" });
    await page.locator("h1").waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator("[data-testid=design-reference]").count(), scenario.reference ? 1 : 0);
    const observation = await page.evaluate(() => ({
      heading: document.querySelector("h1")?.textContent,
      bodyFont: getComputedStyle(document.body).fontFamily,
      headingFont: getComputedStyle(document.querySelector("h1")).fontFamily,
      cls: window.__fontShift,
      scrollWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      fonts: [...document.fonts].map(font => ({ family: font.family, weight: font.weight, status: font.status })),
      resources: performance.getEntriesByType("resource").filter(entry => /\.woff2|\/assets\//.test(entry.name)).map(entry => ({ path: new URL(entry.name).pathname, bytes: entry.encodedBodySize, durationMs: Math.round(entry.duration) })),
    }));
    assert.match(observation.bodyFont, /Inter/);
    assert.match(observation.headingFont, /Manrope/);
    assert.equal(observation.scrollWidth, observation.viewportWidth);
    assert.ok(observation.cls < 0.1, `Font layout shift is ${observation.cls}`);
    let contrast = null;
    let renderedFonts = null;
    let focus = null;
    if (scenario.reference) {
      assert.deepEqual(apiRequests, [], "Reference must not load authenticated or business data");
      contrast = await page.evaluate(() => {
        function luminance(color) {
          const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(value => value / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
          return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
        }
        function ratio(a, b) { const x = luminance(a); const y = luminance(b); return Math.round(((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)) * 100) / 100; }
        const pairs = [];
        for (const surface of document.querySelectorAll("[data-surface]")) {
          const bg = getComputedStyle(surface).backgroundColor;
          const label = surface.querySelector("p");
          pairs.push({ pair: `${surface.dataset.surface}/text`, ratio: ratio(getComputedStyle(label).color, bg), minimum: 4.5 });
          const secondary = surface.querySelector(".text-secondary");
          if (secondary) pairs.push({ pair: `${surface.dataset.surface}/secondary`, ratio: ratio(getComputedStyle(secondary).color, bg), minimum: 4.5 });
          const input = surface.querySelector("input");
          if (input) {
            pairs.push({ pair: `${surface.dataset.surface}/control`, ratio: ratio(getComputedStyle(input).borderColor, bg), minimum: 3 });
            input.focus();
            pairs.push({ pair: `${surface.dataset.surface}/focus`, ratio: ratio(getComputedStyle(input).outlineColor, bg), minimum: 3 });
          } else {
            const button = surface.querySelector("button");
            button.focus();
            pairs.push({ pair: "navigation/focus", ratio: ratio(getComputedStyle(button).outlineColor, bg), minimum: 3 });
            pairs.push({ pair: "navigation/selected", ratio: ratio(getComputedStyle(button).color, getComputedStyle(button).backgroundColor), minimum: 4.5 });
          }
          const button = surface.querySelector("button");
          if (input) pairs.push({ pair: `${surface.dataset.surface}/action`, ratio: ratio(getComputedStyle(button).color, getComputedStyle(button).backgroundColor), minimum: 4.5 });
        }
        for (const state of document.querySelectorAll("[data-tone]")) pairs.push({ pair: state.dataset.tone, ratio: ratio(getComputedStyle(state).color, getComputedStyle(state).backgroundColor), minimum: 4.5 });
        return pairs;
      });
      for (const pair of contrast) assert.ok(pair.ratio >= pair.minimum, `${pair.pair}: ${pair.ratio} < ${pair.minimum}`);
      await page.keyboard.press("Tab");
      await page.locator("[data-surface=surface] input").focus();
      focus = await page.locator("[data-surface=surface] input").evaluate(element => ({ width: getComputedStyle(element).outlineWidth, color: getComputedStyle(element).outlineColor, visible: element.matches(":focus-visible") }));
      assert.equal(focus.visible, true);
      assert.equal(focus.width, "2px");
      const cdp = await context.newCDPSession(page);
      await cdp.send("DOM.enable");
      await cdp.send("CSS.enable");
      const { root } = await cdp.send("DOM.getDocument");
      renderedFonts = {};
      for (const selector of ["[data-testid=heading-glyphs]", "[data-testid=body-glyphs]"]) {
        const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
        const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
        assert.ok(fonts.length > 0);
        assert.ok(fonts.every(font => font.isCustomFont), `Fallback glyph in ${selector}: ${JSON.stringify(fonts)}`);
        renderedFonts[selector] = fonts;
      }
      await page.emulateMedia({ reducedMotion: "reduce" });
      assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--an-duration-normal").trim()), "0.01ms");
      await page.emulateMedia({ reducedMotion: "no-preference" });
    }
    await page.screenshot({ path: `${output}${scenario.id}.png`, fullPage: true });
    assert.deepEqual(blocked, [], "No external asset requests are allowed");
    assert.deepEqual(errors, []);
    scenarios.push({ ...scenario, ...observation, contrast, renderedFonts, focus, apiRequests, blockedExternalRequests: blocked, errors });
    await context.close();
  }
  const assets = [];
  for (const name of await readdir(new URL("../dist/assets/", import.meta.url))) {
    const bytes = await readFile(new URL(`../dist/assets/${name}`, import.meta.url));
    assets.push({ name, bytes: bytes.length, gzipBytes: gzipSync(bytes).length });
    if (name.endsWith(".js")) assert.doesNotMatch(bytes.toString(), /Workspace design reference|design-reference|DesignReference/, "Development harness leaked into production JS");
  }
  await writeFile(`${output}assets.json`, `${JSON.stringify({ browser: browser.version(), node: process.version, platform: process.platform, fixtureOnly: true, fontBytes: manifest.reduce((sum, font) => sum + font.bytes, 0), assets, scenarios }, null, 2)}\n`);
} finally { await browser.close(); }
console.log(`Session 02 asset checks passed. Evidence: ${output}`);
