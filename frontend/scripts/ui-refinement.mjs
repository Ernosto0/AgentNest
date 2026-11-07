// Reuse the route-specific fixture journeys without overwriting historical evidence.
// Run after npm run build and preview on 127.0.0.1:5185. No real APIs are contacted.
import { readFile, writeFile, unlink, mkdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
const suites = process.argv.slice(2);
if (!suites.length) throw new Error('Supply fixture suite names (e.g. shell today inbox).');
const results = await readFile('../docs/ui-refinement/checks/results.json', 'utf8').then(JSON.parse).catch(() => []);
await mkdir('../docs/ui-refinement/checks', { recursive: true });
for (const suite of suites) {
  if (!/^[a-z-]+$/.test(suite)) throw new Error('Invalid suite name');
  const source = await readFile(`scripts/ui-${suite}.mjs`, 'utf8');
  const target = `scripts/.refinement-${suite}.mjs`;
  let adapted = source.replaceAll(/\.\.\/\.\.\/docs\/implementation\/phase-8\.5-sessions\/evidence\/s\d+\/?/g, `../../docs/ui-refinement/checks/${suite}/`)
    .replaceAll('width: 360', 'width: 1024')
    .replaceAll('.disableRules(["color-contrast"])', '');
  if (!source.includes('.on("pageerror"')) {
    adapted = adapted.replace('const page = await context.newPage();', 'const page = await context.newPage(); const refinementErrors = []; page.on("pageerror", error => refinementErrors.push(error.message));');
    adapted = adapted.replaceAll('await context.close();', 'assert.deepEqual(refinementErrors, [], "No browser runtime errors"); await context.close();');
  }
  // Historical fixture mistakes: use the real action and the actual fact substring.
  if (suite === 'entry') {
    adapted = adapted.replace('title: "Authentication required", status: 401', 'title: "Authentication required", status: 401, code: "AUTH_REQUIRED"');
    adapted = adapted.replace('const loginScan =', 'await page.locator("input[type=email]").waitFor();\n        const loginScan =');
  }
  if (suite === 'approvals') adapted = adapted.replace('action: "fact.change"', 'action: "command.update_fact"');
  if (suite === 'reports') {
    adapted = adapted.replaceAll('conversations_inbound', 'inbound_messages').replaceAll('posts_published', 'content_published');
    adapted = adapted.replaceAll('await page.screenshot(', 'assert.equal((await page.locator("main").innerText()).includes("reports.metrics."), false, "Report labels are translated"); await page.screenshot(');
    adapted = adapted.replace('// 2. Visit Metric', 'await page.screenshot({ path: path.join(evidenceDir, `${engine.name}-${scenario.label}-overview.png`), fullPage: true });\n        // 2. Visit Metric');
  }
  if (suite === 'activity') {
    adapted = adapted.replace('workspace_id: "ws-activity-test",', 'workspace_id: "ws-activity-test", workspace_name: "Gölkent Test",');
    adapted = adapted.replace('// 2. Notification Center', 'if (scenario.role !== "staff") await page.screenshot({ path: path.resolve(evidenceDir, `${browserName}-${scenario.label}-timeline.png`), fullPage: true });\n    // 2. Notification Center');
  }
  if (['settings', 'connections', 'health-dev'].includes(suite)) {
    adapted = adapted.replace(/workspace_id: "(ws-[a-z]+-test)",/, 'workspace_id: "$1", workspace_name: "Gölkent Test",');
  }
  if (suite === 'settings') {
    adapted = adapted.replace('if (pathName === "/api/v1/meta")', 'if (pathName.endsWith("/deletion-status")) return route.fulfill({ json: { is_deleting: false } }); if (pathName.endsWith("/auth/sessions")) return route.fulfill({ json: [] }); if (pathName === "/api/v1/meta")');
  }
  if (suite === 'connections') {
    adapted = adapted.replace('if (pathName === "/api/v1/meta")', 'if (pathName.endsWith("/channels/links")) return route.fulfill({ json: [] }); if (pathName === "/api/v1/meta")');
    adapted = adapted.replace('// 2. Members Page', 'await page.screenshot({ path: path.resolve(evidenceDir, `${browserName}-${scenario.label}-accounts.png`), fullPage: true });\n    // 2. Members Page');
  }
  if (suite === 'health-dev') {
    adapted = adapted.replace('// 2. Dev Panel', 'await page.screenshot({ path: path.resolve(evidenceDir, `${browserName}-${scenario.label}-health.png`), fullPage: true });\n    // 2. Dev Panel');
    adapted = adapted.replace('// 3. 404 Fallback Page', 'await page.screenshot({ path: path.resolve(evidenceDir, `${browserName}-${scenario.label}-dev.png`), fullPage: true });\n    // 3. 404 Fallback Page');
    adapted = adapted.replace('const h1Text =', 'assert.equal((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations.length, 0, "Workspace not-found accessibility");\n    const h1Text =');
  }
  if (suite === 'knowledge') adapted = adapted.replaceAll('code: "instagram_connected"', 'code: "account_connected"').replaceAll('status: "attention"', 'status: "missing"');
  if (suite === 'conversation') {
    const text = 'Merhaba Ayşe Hanım! Aylık fitness üyelik ücretimiz 6.000 ₺ / ay.';
    const value = '6.000 ₺ / ay';
    adapted = adapted.replace('span: [43, 56]', `span: [${text.indexOf(value)}, ${text.indexOf(value) + value.length}]`);
  }
  await writeFile(target, adapted);
  console.log(`Running ${suite}`);
  const started = Date.now();
  const child = spawn(process.execPath, [target], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, UI_ENTRY_ORIGIN: 'http://127.0.0.1:5185' } });
  let output = '';
  child.stdout.on('data', chunk => { output += chunk; });
  child.stderr.on('data', chunk => { output += chunk; });
  const code = await new Promise(resolve => child.on('close', resolve));
  await unlink(target);
  await writeFile(`../docs/ui-refinement/checks/${suite}.log`, output);
  await writeFile(`../docs/ui-refinement/checks/${suite}-result.json`, JSON.stringify({ suite, code, durationMs: Date.now() - started }, null, 2));
  const result = { suite, code, durationMs: Date.now() - started };
  const index = results.findIndex(previous => previous.suite === suite);
  if (index < 0) results.push(result);
  else results[index] = result;
  await writeFile('../docs/ui-refinement/checks/results.json', JSON.stringify(results, null, 2));
  console.log(`${suite}: ${code === 0 ? 'PASS' : 'FAIL'}\n${output.slice(-1800)}`);
}
process.exitCode = results.some(result => suites.includes(result.suite) && result.code !== 0) ? 1 : 0;
