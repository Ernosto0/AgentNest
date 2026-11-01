import { chromium, webkit } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const evidenceDir = path.resolve(__dirname, "../../docs/implementation/phase-8.5-sessions/evidence/s19");
await fs.mkdir(evidenceDir, { recursive: true });

const frontendRoot = path.resolve(__dirname, "..");
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const scenarios = [
  {
    label: "tr-phone-360",
    viewport: { width: 360, height: 740 },
    locale: "tr",
    role: "owner",
  },
  {
    label: "en-phone-390",
    viewport: { width: 390, height: 844 },
    locale: "en",
    role: "owner",
  },
  {
    label: "tr-tablet-768",
    viewport: { width: 768, height: 1024 },
    locale: "tr",
    role: "manager",
  },
  {
    label: "en-desktop-1440",
    viewport: { width: 1440, height: 900 },
    locale: "en",
    role: "staff",
  },
];

const mockTemplate = [
  {
    identifier: "pricing-monthly",
    key: "pricing.membership_monthly",
    category: "pricing",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    description: { tr: "Standart aylık paket ücreti", en: "Standard monthly fee" },
    value_types: ["money"],
    allowed_values: [],
    pattern: null,
    criticality: "critical",
    fact_ids: ["f-price-01"],
  },
  {
    identifier: "hours-weekly",
    key: "hours.weekly",
    category: "hours",
    label: { tr: "Haftalık çalışma saatleri", en: "Weekly hours" },
    description: { tr: "Açılış ve kapanış saatleri", en: "Opening and closing hours" },
    value_types: ["weekly_hours"],
    allowed_values: [],
    pattern: null,
    criticality: "standard",
    fact_ids: ["f-hours-01"],
  },
];

const mockFacts = [
  {
    id: "f-price-01",
    key: "pricing.membership_monthly",
    category: "pricing",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    value_type: "money",
    value: { amount: "1250.00", currency: "TRY", unit: "month" },
    state: "verified",
    current_version: 3,
    source_type: "owner_entry",
    valid_from: null,
    valid_until: null,
    updated_at: "2026-10-25T14:30:00Z",
  },
  {
    id: "f-hours-01",
    key: "hours.weekly",
    category: "hours",
    label: { tr: "Haftalık çalışma saatleri", en: "Weekly hours" },
    value_type: "weekly_hours",
    value: {
      schedule: [
        { days: ["mon", "tue", "wed", "thu", "fri"], ranges: [["08:00", "22:00"]] },
        { days: ["sat"], ranges: [["09:00", "20:00"]] },
      ],
      exceptions: [{ date: "2026-12-31", closed: false, ranges: [["09:00", "15:00"]] }],
    },
    state: "verified",
    current_version: 2,
    source_type: "owner_entry",
    valid_from: null,
    valid_until: null,
    updated_at: "2026-10-26T10:00:00Z",
  },
];

const mockCandidates = [
  {
    id: "cand-01",
    fact_key: "pricing.membership_monthly",
    fact_label: { tr: "Aylık üyelik", en: "Monthly membership" },
    relation: "contest",
    proposed_value: { amount: "1400.00", currency: "TRY", unit: "month" },
    proposed_display: "1.400,00 TL / ay",
    current_display: "1.250,00 TL / ay",
    proposed_by_name: "Staff Aylin",
    source_type: "staff_proposal",
    source_excerpt: "Instagram DM'de fiyatın 1.400 TL olduğu konuşuluyor.",
    created_at: "2026-10-28T09:15:00Z",
  },
  {
    id: "cand-02",
    fact_key: "pricing.student_discount",
    fact_label: { tr: "Öğrenci indirimi", en: "Student discount" },
    relation: "new",
    proposed_value: { text: "%20 indirim tüm üyeliklerde geçerlidir." },
    proposed_display: "%20 indirim tüm üyeliklerde geçerlidir.",
    current_display: null,
    proposed_by_name: null,
    source_type: "bio_extract",
    source_excerpt: "Bio: Öğrencilere %20 indirim fırsatı!",
    created_at: "2026-10-29T11:00:00Z",
  },
];

const mockVersions = [
  {
    version: 3,
    display: "1.250,00 TL / ay",
    change_kind: "updated",
    source_type: "owner_entry",
    actor_name: "Owner Deniz",
    reason: "Sonbahar sezonu fiyat güncellemesi",
    created_at: "2026-10-25T14:30:00Z",
  },
  {
    version: 2,
    display: "1.000,00 TL / ay",
    change_kind: "updated",
    source_type: "owner_entry",
    actor_name: "Owner Deniz",
    reason: "Yaz dönemi kampanyası sonrası",
    created_at: "2026-08-01T10:00:00Z",
  },
  {
    version: 1,
    display: "850,00 TL / ay",
    change_kind: "created",
    source_type: "template_default",
    actor_name: null,
    reason: null,
    created_at: "2026-06-01T09:00:00Z",
  },
];

const engines = [
  { name: "chromium", launcher: chromium },
  { name: "webkit", launcher: webkit },
];

const ws = "ws-fact-test";
const name = "Ornek Salon";
const base = `/w/${ws}`;

const auditResults = [];

try {
  for (const engine of engines) {
  const browser = await engine.launcher.launch({ headless: true });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      locale: scenario.locale === "tr" ? "tr-TR" : "en-US",
    });

    const page = await context.newPage();

    try {
      await page.addInitScript(
        ({ lang }) => {
          localStorage.setItem("agentnest.locale", lang);
          localStorage.setItem("i18nextLng", lang);
        },
        { lang: scenario.locale },
      );

      const currentMe = {
        user: {
          id: `u-${scenario.role}`,
          email: `${scenario.role}@agentnest.example`,
          display_name: `${scenario.role.toUpperCase()} User`,
          ui_locale: scenario.locale,
        },
        csrf_token: "fixture-csrf-token",
        memberships: [
          {
            workspace_id: ws,
            workspace_name: name,
            workspace_slug: "ornek-salon",
            role: scenario.role,
            is_active: true,
          },
        ],
      };

      await page.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        if (!url.pathname.startsWith("/api/")) return route.continue();

        const pathname = url.pathname;
        const respond = (body, status = 200) =>
          route.fulfill({
            status,
            contentType: "application/json",
            body: JSON.stringify(body),
          });

        if (pathname === "/api/v1/meta") {
          return respond({
            product_name: "AgentNest",
            demo_tools_enabled: true,
            llm_mode: "fake",
            supported_locales: ["tr", "en"],
            instagram_providers: ["mock"],
            mock_requires_demo_workspace: false,
          });
        }

        if (pathname === "/api/v1/auth/me") return respond(currentMe);

        if (pathname === `/api/v1/workspaces/${ws}`) {
          return respond({
            id: ws,
            name,
            slug: "ornek-salon",
            business_category: "fitness",
            market: "tr",
            default_locale: scenario.locale,
            reply_languages: [scenario.locale],
            timezone: "Europe/Istanbul",
            currency: "TRY",
            is_demo: true,
            status: "active",
            created_at: "2026-10-15T12:00:00Z",
            settings: {},
          });
        }

        if (pathname.endsWith("/facts/template")) return respond(mockTemplate);

        if (pathname.endsWith("/facts")) return respond({ items: mockFacts, next_cursor: null });

        if (pathname.includes("/facts/f-price-01/versions")) return respond({ items: mockVersions });

        if (pathname.endsWith("/fact-candidates")) return respond({ items: mockCandidates, next_cursor: null });

        if (pathname.endsWith("/readiness")) {
          return respond({
            score: 0.85,
            level: "ready",
            missing_critical: [],
            attention_required: [],
            requirements: [],
          });
        }

        if (pathname.endsWith("/notifications")) {
          return respond({ items: [], unread_count: 0, next_cursor: null });
        }

        return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
      });

      // 1. Visit Category Page (Route R20, Controls K03–K05)
      await page.goto(`${origin}${base}/more/knowledge/pricing`, { waitUntil: "networkidle" });

      // Verify category page loaded
      const priceTitle = scenario.locale === "tr" ? "Aylık üyelik" : "Monthly membership";
      await page.getByText(priceTitle).first().waitFor({ state: "visible", timeout: 8000 });

      // Open Fact Editor Sheet
      const editBtnName = scenario.role === "staff"
        ? (scenario.locale === "tr" ? "Değişiklik öner" : "Suggest a change")
        : (scenario.locale === "tr" ? "Düzenle" : "Edit");
      await page.getByRole("button", { name: editBtnName }).first().click();

      // Verify Fact Editor Sheet is open
      const sheetSave = scenario.role === "staff"
        ? (scenario.locale === "tr" ? "Öner" : "Suggest a value")
        : (scenario.locale === "tr" ? "Kaydet" : "Save");
      await page.getByRole("button", { name: sheetSave }).waitFor({ state: "visible", timeout: 5000 });

      // Check overflow in editor sheet
      let overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return {
          clientWidth: doc.clientWidth,
          scrollWidth: doc.scrollWidth,
          hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
        };
      });
      assert.equal(overflow.hasOverflow, false, `Horizontal overflow on fact editor in ${engine.name} ${scenario.label}`);

      // Run Axe audit on Fact Editor Sheet
      let axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      assert.equal(axe.violations.length, 0, `Axe violations on fact editor in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

      // Close Editor Sheet
      const closeBtnName = scenario.locale === "tr" ? "Kapat" : "Close";
      await page.getByRole("button", { name: closeBtnName }).first().click();

      // Open History Sheet
      const historyBtnName = scenario.locale === "tr" ? "Geçmiş" : "History";
      await page.getByRole("button", { name: historyBtnName }).first().click();

      // Verify history sheet loaded versions
      const v3Text = scenario.locale === "tr" ? "Sürüm 3" : "Version 3";
      await page.getByText(v3Text).first().waitFor({ state: "visible", timeout: 5000 });

      // Run Axe audit on History Sheet
      axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      assert.equal(axe.violations.length, 0, `Axe violations on history sheet in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

      // Close History Sheet
      await page.getByRole("button", { name: closeBtnName }).first().click();

      // 2. Visit Suggestions Page (Route R21, Control K17)
      await page.goto(`${origin}${base}/more/knowledge/suggestions`, { waitUntil: "networkidle" });

      const suggTitle = scenario.locale === "tr" ? "Öneriler" : "Suggestions";
      await page.getByRole("heading", { name: suggTitle }).waitFor({ state: "visible", timeout: 8000 });

      // Check overflow on suggestions
      overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return {
          clientWidth: doc.clientWidth,
          scrollWidth: doc.scrollWidth,
          hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
        };
      });
      assert.equal(overflow.hasOverflow, false, `Horizontal overflow on suggestions in ${engine.name} ${scenario.label}`);

      // Run Axe audit on Suggestions
      axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      assert.equal(axe.violations.length, 0, `Axe violations on suggestions in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

      // Screenshot for evidence
      const shotPath = path.join(evidenceDir, `${engine.name}-${scenario.label}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });

      auditResults.push({
        engine: engine.name,
        scenario: scenario.label,
        passed: true,
        violations: 0,
      });
    } finally {
      await context.close();
    }
  }

  await browser.close();
}

  await fs.writeFile(
    path.join(evidenceDir, "fact-editors.json"),
    JSON.stringify(auditResults, null, 2),
    "utf8",
  );

  console.log("Session 19 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
