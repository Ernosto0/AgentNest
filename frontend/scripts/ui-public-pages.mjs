import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const origin = 'http://127.0.0.1:5185';
const output = '../docs/ui-refinement/checks/public-pages';
await mkdir(output, { recursive: true });
const results = [];
for (const engine of [chromium, webkit]) {
  const browser = await engine.launch();
  try {
    for (const width of [390, 768, 1024, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, locale: 'en', serviceWorkers: 'block' });
      try {
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await context.route('**/*', route => {
          const url = new URL(route.request().url());
          if (url.origin !== origin) return route.abort();
          if (!url.pathname.startsWith('/api/')) return route.continue();
          if (url.pathname.endsWith('/meta')) return route.fulfill({ json: { product_name: 'AgentNest', demo_tools_enabled: false, llm_mode: 'fake' } });
          return route.fulfill({ status: 401, json: { code: 'AUTH_REQUIRED', status: 401, params: {} } });
        });
        for (const route of ['/privacy', '/data-deletion', '/reset-password', '/reset-password/fixture-token', '/unknown-page']) {
          await page.goto(`${origin}${route}`, { waitUntil: 'networkidle' });
          await page.evaluate(() => document.fonts.ready);
          assert.equal(await page.getByRole('heading', { level: 1 }).count(), 1);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
          assert.equal(overflow, 0, `${route} at ${width}px`);
          const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
          assert.deepEqual(scan.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) })), []);
          assert.deepEqual(errors, []);
          if (width === 390 || width === 1440) await page.screenshot({ path: `${output}/${engine.name()}-${width}-${route.replaceAll('/', '_')}.png`, fullPage: true });
          results.push({ engine: engine.name(), route, width, errors: [], overflow, violations: 0 });
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(`${output}/results.json`, JSON.stringify(results, null, 2));
console.log(`Public pages: ${results.length} checks passed.`);
