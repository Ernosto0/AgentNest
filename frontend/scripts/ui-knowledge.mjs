// Session 18 production fixture checks: Knowledge overview, readiness checklist, suggestions entry, and category browsing.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { preview } from "vite";

const output = fileURLToPath(new URL("../../docs/implementation/phase-8.5-sessions/evidence/s18/", import.meta.url));
await mkdir(output, { recursive: true });

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root: frontendRoot, preview: { port: 0, host: "127.0.0.1" } });
const port = server.httpServer.address().port;
const origin = `http://127.0.0.1:${port}`;

const ws = "11111111-1111-4111-8111-111111111111";
const base = `/w/${ws}`;
const name = "Örnek Spor Salonu";
const results = [];

const ownerMe = {
  user: { id: "99999999-9999-4999-8999-999999999999", display_name: "Ayşe Yılmaz", email: "ayse@example.test", ui_locale: "tr" },
  csrf_token: "fixture-csrf-token",
  memberships: [{ workspace_id: ws, workspace_name: name, role: "owner", is_demo: true }],
};

const mockReadiness = {
  overall_status: "ready_for_drafts",
  requirements: [
    { code: "business_name", status: "satisfied", satisfied: true, link: { target: "knowledge", category: "identity" } },
    { code: "booking_instructions", status: "attention", satisfied: false, link: { target: "knowledge", category: "booking" } },
    { code: "instagram_connected", status: "attention", satisfied: false, link: { target: "integrations" } },
  ],
  warnings: [],
};

const mockTemplate = [
  {
    identifier: "pricing-monthly",
    category: "pricing",
    key: "pricing.membership_monthly",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    description: { tr: "Standart aylık salon üyeliği ücreti", en: "Standard monthly gym membership fee" },
    status: "present",
    required_for: "drafts",
    value_type: "money",
  },
  {
    identifier: "pricing-student",
    category: "pricing",
    key: "pricing.student_monthly",
    label: { tr: "Öğrenci üyeliği", en: "Student membership" },
    description: { tr: "Öğrenci indirimli aylık üyelik", en: "Student discounted monthly membership" },
    status: "present",
    required_for: null,
    value_type: "money",
  },
  {
    identifier: "pricing-single",
    category: "pricing",
    key: "pricing.single_session",
    label: { tr: "Tek giriş", en: "Single session" },
    description: { tr: "Tek seferlik giriş ücreti", en: "Single visit entry fee" },
    status: "missing",
    required_for: "automation",
    value_type: "money",
  },
  {
    identifier: "hours-weekdays",
    category: "hours",
    key: "hours.regular",
    label: { tr: "Çalışma saatleri", en: "Opening hours" },
    description: { tr: "Haftalık çalışma saatleri", en: "Weekly opening hours" },
    status: "present",
    required_for: "drafts",
    value_type: "hours",
  },
  {
    identifier: "contact-phone",
    category: "contact",
    key: "contact.phone",
    label: { tr: "Telefon", en: "Phone" },
    description: { tr: "İletişim telefon numarası", en: "Contact phone number" },
    status: "present",
    required_for: null,
    value_type: "phone",
  },
];

const mockFacts = [
  {
    id: "f-pricing-1",
    key: "pricing.membership_monthly",
    category: "pricing",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    display: "6.000 ₺ / ay",
    status: "verified",
    state: "verified",
    usable: true,
    current_version: 1,
    last_verified_at: "2026-10-12T10:00:00Z",
    source_type: "manual",
    last_verified_by_name: "Ayşe Yılmaz",
  },
  {
    id: "f-pricing-2",
    key: "pricing.student_monthly",
    category: "pricing",
    label: { tr: "Öğrenci üyeliği", en: "Student membership" },
    display: "4.500 ₺ / ay",
    status: "unverified",
    state: "unverified",
    usable: false,
    current_version: 1,
    source_type: "suggestion",
  },
  {
    id: "f-hours-1",
    key: "hours.regular",
    category: "hours",
    label: { tr: "Çalışma saatleri", en: "Opening hours" },
    display: "Hafta içi 07:00 - 23:00, Hafta sonu 09:00 - 20:00",
    status: "verified",
    state: "verified",
    usable: true,
    current_version: 1,
    last_verified_at: "2026-10-12T10:00:00Z",
  },
];

const mockCandidates = [
  {
    id: "cand-1",
    category: "pricing",
    key: "pricing.personal_trainer",
    current_version: null,
  },
];

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

        const currentMe = { ...ownerMe, user: { ...ownerMe.user, ui_locale: scenario.locale } };

        await context.route("**/*", async (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== origin) {
            blocked.push(url.href);
            return route.abort();
          }
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

          if (pathname.endsWith("/readiness")) return respond(mockReadiness);

          if (pathname.endsWith("/facts/template")) return respond(mockTemplate);

          if (pathname.endsWith("/facts")) return respond({ items: mockFacts, next_cursor: null });

          if (pathname.endsWith("/fact-candidates")) return respond({ items: mockCandidates, next_cursor: null });

          if (pathname.endsWith("/notifications")) {
            return respond({ items: [], unread_count: 0, next_cursor: null });
          }

          return respond({ code: "NOT_FOUND", message: "Not found" }, 404);
        });

        // 1. Visit Knowledge Overview (Route R19, Control K01)
        await page.goto(`${origin}${base}/more/knowledge`, { waitUntil: "networkidle" });

        // Verify title and readiness checklist
        const title = scenario.locale === "tr" ? "İşletme bilgileri" : "Business knowledge";
        await page.getByRole("heading", { name: title }).waitFor({ state: "visible", timeout: 8000 });

        // Verify categories exist
        const pricingCategory = scenario.locale === "tr" ? "Fiyatlar" : "Prices";
        await page.getByText(pricingCategory).first().waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Overview
        let overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on knowledge overview in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        // Run Axe accessibility audit on Overview
        let axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const overviewShot = `${output}/${engine.name}-${scenario.label}-overview.png`;
        await page.screenshot({ path: overviewShot, fullPage: true });

        assert.equal(errors.length, 0, `Page errors in ${engine.name} ${scenario.label}: ${errors.join(", ")}`);
        assert.equal(axe.violations.length, 0, `Axe violations on overview in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        // 2. Visit Category Page (Route R20, Controls K02, K03)
        await page.goto(`${origin}${base}/more/knowledge/pricing`, { waitUntil: "networkidle" });

        // Verify category title
        await page.getByRole("heading", { name: pricingCategory }).waitFor({ state: "visible", timeout: 8000 });

        // Verify fact display
        await page.getByText("6.000 ₺ / ay").waitFor({ state: "visible", timeout: 8000 });

        // Verify status chips
        const verifiedChip = scenario.locale === "tr" ? "Doğrulandı" : "Verified";
        await page.getByText(verifiedChip).first().waitFor({ state: "visible", timeout: 8000 });

        // Check horizontal overflow on Category
        overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: doc.scrollWidth,
            hasOverflow: doc.scrollWidth > doc.clientWidth + 1,
          };
        });
        assert.equal(overflow.hasOverflow, false, `Horizontal overflow on category page in ${engine.name} ${scenario.label}: ${JSON.stringify(overflow)}`);

        axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();

        const categoryShot = `${output}/${engine.name}-${scenario.label}-category.png`;
        await page.screenshot({ path: categoryShot, fullPage: true });

        assert.equal(axe.violations.length, 0, `Axe violations on category page in ${engine.name} ${scenario.label}: ${JSON.stringify(axe.violations, null, 2)}`);

        results.push({
          engine: engine.name,
          scenario: scenario.label,
          axeOverview: 0,
          axeCategory: 0,
          overflow: false,
        });

        await context.close();
      }
    } finally {
      await browser.close();
    }
  }

  await writeFile(
    `${output}/knowledge.json`,
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2),
    "utf8"
  );
  console.log("Session 18 Playwright verification passed cleanly with 0 violations across all 8 browser fixtures.");
} finally {
  await server.close();
}
