// Session 05 production fixture checks: login, invites, picker, creation wizard.
// Does not start/reset a database or call real APIs.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s05/", import.meta.url));
await mkdir(output, { recursive: true });

let server;
let origin = process.env.UI_ENTRY_ORIGIN;
if (!origin) {
  try {
    server = await preview({ preview: { port: 5185, host: "127.0.0.1" } });
    origin = "http://127.0.0.1:5185";
  } catch (err) {
    origin = "http://127.0.0.1:5185";
  }
}

const ws = "11111111-1111-4111-8111-111111111111";
const longName = "Örnek Atölye / Example Studio with an intentionally long workspace name for wrapping tests";
const results = [];

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

        let currentUser = null;
        let memberships = [
          { workspace_id: ws, workspace_name: longName, role: "owner", is_demo: true },
          { workspace_id: "22222222-2222-4222-8222-222222222222", workspace_name: "Second Studio", role: "staff", is_demo: false },
        ];

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
                mock_requires_demo_workspace: false,
              }),
            });
          }

          if (pathname === "/api/v1/auth/me") {
            if (currentUser) {
              return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                  user: currentUser,
                  csrf_token: "csrf-token-s05",
                  memberships,
                }),
              });
            }
            return route.fulfill({
              status: 401,
              contentType: "application/problem+json",
              body: JSON.stringify({ type: "urn:agentnest:error:auth_required", title: "Authentication required", status: 401 }),
            });
          }

          if (pathname === "/api/v1/auth/login" && method === "POST") {
            currentUser = { id: "99999999-9999-4999-8999-999999999999", display_name: "Test User", email: "test@example.test", ui_locale: scenario.locale };
            return route.fulfill({ status: 204 });
          }

          if (pathname === "/api/v1/auth/logout" && method === "POST") {
            currentUser = null;
            return route.fulfill({ status: 204 });
          }

          if (pathname === "/api/v1/invites/accept" && method === "POST") {
            const body = JSON.parse(route.request().postData() || "{}");
            if (body.token === "invalid-token") {
              return route.fulfill({
                status: 400,
                contentType: "application/problem+json",
                body: JSON.stringify({ type: "urn:agentnest:error:invite_invalid", title: "Invalid invite", status: 400 }),
              });
            }
            currentUser = { id: "88888888-8888-4888-8888-888888888888", display_name: body.display_name || "Invited User", email: body.email || "invited@example.test", ui_locale: scenario.locale };
            memberships.push({ workspace_id: ws, workspace_name: "Gölkent Fitness", role: "manager", is_demo: false });
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ workspace_id: ws, workspace_name: "Gölkent Fitness", role: "manager" }),
            });
          }

          if (pathname === "/api/v1/workspaces" && method === "POST") {
            const body = JSON.parse(route.request().postData() || "{}");
            const newWs = {
              id: "33333333-3333-4333-8333-333333333333",
              name: body.name,
              slug: "new-ws",
              business_category: body.business_category,
              market: body.market,
              default_locale: body.default_locale,
              reply_languages: [body.default_locale],
              timezone: body.timezone,
              currency: body.currency,
              is_demo: false,
              status: "active",
              created_at: new Date().toISOString(),
              settings: { automation_reviewed_at: null, disclosure_enabled: true, disclosure_text: { tr: "", en: "" }, daily_report_hour: 20, publish_max_delay_minutes: 1440 },
            };
            memberships.push({ workspace_id: newWs.id, workspace_name: newWs.name, role: "owner", is_demo: false });
            return route.fulfill({
              status: 201,
              contentType: "application/json",
              body: JSON.stringify(newWs),
            });
          }

          if (pathname.startsWith("/api/v1/workspaces/")) {
            return route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [], next_cursor: null, level: "not_ready", requirements: [] }),
            });
          }

          return route.fulfill({ status: 404 });
        });

        // 1. LOGIN SCREEN
        currentUser = null;
        await page.goto(`${origin}/login`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);
        const loginScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(loginScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);

        const docSize1 = await page.evaluate(() => ({ viewport: innerWidth, doc: document.documentElement.scrollWidth }));
        assert.equal(docSize1.viewport, docSize1.doc, "No horizontal overflow on login");

        const idPrefix = `${engine.name}-${scenario.label}`;
        await page.screenshot({ path: `${output}/${idPrefix}-login.png` });

        // 2. INVITE SCREEN (Signed out)
        await page.goto(`${origin}/invite/tok-valid-123`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);
        const inviteScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(inviteScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);
        await page.screenshot({ path: `${output}/${idPrefix}-invite-signed-out.png` });

        // 3. WORKSPACE PICKER SCREEN (Signed in)
        currentUser = { id: "99999999-9999-4999-8999-999999999999", display_name: "Test User", email: "test@example.test", ui_locale: scenario.locale };
        await page.goto(`${origin}/`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);
        const pickerScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(pickerScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);

        const docSizePicker = await page.evaluate(() => ({ viewport: innerWidth, doc: document.documentElement.scrollWidth }));
        assert.equal(docSizePicker.viewport, docSizePicker.doc, "No horizontal overflow on picker with long names");
        await page.screenshot({ path: `${output}/${idPrefix}-picker.png` });

        // 4. WIZARD STEP 1 -> STEP 2 -> STEP 3 -> STEP BACK -> LEAVE
        await page.goto(`${origin}/workspaces/new`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);

        // Step 1
        const wizardScan1 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(wizardScan1.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);
        await page.screenshot({ path: `${output}/${idPrefix}-wizard-step1.png` });

        const nextBtn = scenario.locale === "tr" ? "Devam" : "Continue";
        const prevBtn = scenario.locale === "tr" ? "Geri" : "Back";
        const backLink = scenario.locale === "tr" ? "Çalışma alanlarıma dön" : "Back to my workspaces";

        // Type business name and continue to Step 2
        await page.locator('input[name="business_name"]').fill("Test Pilates Studio");
        await page.getByRole("button", { name: nextBtn }).click();

        // Step 2
        await page.locator('input[type="radio"]').first().check();
        const wizardScan2 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(wizardScan2.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);
        await page.screenshot({ path: `${output}/${idPrefix}-wizard-step2.png` });

        // Continue to Step 3
        await page.getByRole("button", { name: nextBtn }).click();

        // Step 3
        const wizardScan3 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(wizardScan3.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);
        await page.screenshot({ path: `${output}/${idPrefix}-wizard-step3.png` });

        // Go Back to step 2 then step 1 and verify input retention
        await page.getByRole("button", { name: prevBtn }).click();
        assert.equal(await page.locator('input[type="radio"]').first().isChecked(), true, "Step 2 retained category");
        await page.getByRole("button", { name: prevBtn }).click();
        assert.equal(await page.locator('input[name="business_name"]').inputValue(), "Test Pilates Studio", "Step 1 retained name");

        // Click Back link to trigger dirty blocker
        await page.getByRole("link", { name: backLink }).click();
        const leaveDialog = page.getByRole("dialog");
        await leaveDialog.waitFor();
        const blockerScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(blockerScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), []);
        await page.screenshot({ path: `${output}/${idPrefix}-wizard-leave-dialog.png` });

        // Close blocker
        await page.getByRole("button", { name: scenario.locale === "tr" ? "Düzenlemeye devam et" : "Keep editing" }).click();
        assert.equal(await page.locator('input[name="business_name"]').inputValue(), "Test Pilates Studio");

        assert.deepEqual(errors, []);
        assert.deepEqual(blocked, []);

        results.push({
          browser: engine.name,
          version: browser.version(),
          ...scenario,
          loginAxeViolations: loginScan.violations.length,
          inviteAxeViolations: inviteScan.violations.length,
          pickerAxeViolations: pickerScan.violations.length,
          wizardStep1AxeViolations: wizardScan1.violations.length,
          wizardStep2AxeViolations: wizardScan2.violations.length,
          wizardStep3AxeViolations: wizardScan3.violations.length,
          blockerAxeViolations: blockerScan.violations.length,
          overflow: false,
          pageErrors: errors.length,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }
} finally {
  if (server) await server.close();
}

await writeFile(
  `${output}/entry.json`,
  `${JSON.stringify({ executedAt: new Date().toISOString(), platform: process.platform, node: process.version, scenarios: results }, null, 2)}\n`,
);

console.log(`Verified ${results.length} onboarding/entry scenarios; evidence: ${output}`);
