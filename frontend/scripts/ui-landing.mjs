import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s26");
await fs.mkdir(evidenceDir, { recursive: true });

const landingRoot = path.resolve(__dirname, "../../landing");
const server = await preview({ root: landingRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const scenarios = [
  {
    label: "tr-phone-360",
    viewport: { width: 360, height: 740 },
    locale: "tr",
  },
  {
    label: "en-phone-390",
    viewport: { width: 390, height: 844 },
    locale: "en",
  },
  {
    label: "tr-tablet-768",
    viewport: { width: 768, height: 1024 },
    locale: "tr",
  },
  {
    label: "en-desktop-1440",
    viewport: { width: 1440, height: 900 },
    locale: "en",
  },
];

const results = [];

for (const browserType of [chromium, webkit]) {
  const browserName = browserType.name();
  const browser = await browserType.launch({ headless: true });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      locale: scenario.locale,
    });

    await context.addInitScript((loc) => {
      window.localStorage.setItem("landing.lang", loc);
    }, scenario.locale);

    const page = await context.newPage();

    // 1. Visit Landing Page
    await page.goto(`${origin}/`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1");

    // 2. Verify Language switcher
    const targetLangBtn = page.locator(`button[lang="${scenario.locale}"]`);
    await assert.doesNotReject(async () => {
      await targetLangBtn.first().waitFor();
    });

    // 3. Check for horizontal overflow
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 1;
    });
    assert.equal(overflow, false, `Horizontal overflow on ${scenario.label}`);

    // 4. Run Axe accessibility audit
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast"])
      .analyze();
    assert.equal(axe.violations.length, 0, `Axe violations on ${scenario.label}: ${JSON.stringify(axe.violations)}`);

    const screenshotPath = path.resolve(evidenceDir, `${browserName}-${scenario.label}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    results.push({
      engine: browserName,
      scenario: scenario.label,
      passed: true,
      violations: axe.violations.length,
    });

    await context.close();
  }

  await browser.close();
}

await fs.writeFile(
  path.resolve(evidenceDir, "landing.json"),
  JSON.stringify(results, null, 2) + "\n",
  "utf8"
);

await server.close();
console.log("Playwright fixture scan complete: 8/8 scenarios passed with 0 Axe violations!");
