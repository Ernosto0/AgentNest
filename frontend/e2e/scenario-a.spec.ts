import { expect, test, type Page } from "@playwright/test";
import { hasHorizontalScroll, navLink, reseedDemo, signInToWorkspace } from "./helpers";

// Scenario A: business onboarding and knowledge (docs/product/acceptance-criteria.md AC-A1…A5).
// All strings are the Turkish ones: the demo users' account language is Turkish.

const OWNER = "owner@demo.local";
const STAFF = "staff@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

test.beforeEach(() => {
  reseedDemo(); // the tests below change facts; every run starts from the same data
});

async function openKnowledge(page: Page) {
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "İşletme bilgileri" }).click();
  await expect(page.getByRole("heading", { name: "İşletme bilgileri", level: 1 })).toBeVisible();
}

async function openPricing(page: Page) {
  await openKnowledge(page);
  await page.getByRole("link", { name: /Fiyatlar/ }).click();
  await expect(page.getByRole("heading", { name: "Fiyatlar", level: 1 })).toBeVisible();
}

test("A1: Home shows the workspace, its readiness and the simulation banner", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);

  await expect(page.getByRole("main").getByText("Gölkent Fitness & Pilates")).toBeVisible();
  await expect(page.getByTestId("simulation-banner")).toContainText("simülasyon");
  await expect(page.getByTestId("simulated-badge").first()).toBeVisible();
  // The seeded gym is ready for drafts; the account and the automation review come in Phase 4.
  await expect(page.getByTestId("readiness-level")).toHaveText("Taslaklar için hazır");
  await expect(page.getByTestId("readiness-level")).toHaveAttribute("data-level", "ready_for_drafts");
  await expect(page.locator('[data-requirement="account_connected"]')).toContainText("Instagram hesabı bağlı");
  expect(await hasHorizontalScroll(page)).toBe(false);
});

test("A2: facts are grouped by category with status, source and verification date", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await openKnowledge(page);

  const pricingRow = page.locator('[data-category="pricing"]');
  await expect(pricingRow).toContainText("Fiyatlar");
  await expect(pricingRow).toContainText("Doğrulanmamış"); // the student price
  expect(await hasHorizontalScroll(page)).toBe(false);

  await pricingRow.click();
  const monthly = page.getByTestId("fact-pricing.membership_monthly");
  await expect(monthly).toContainText("6.000 ₺ / ay");
  await expect(monthly).toContainText("Doğrulandı");
  await expect(monthly).toContainText("tarihinde doğrulandı");
  await expect(monthly).toContainText("Demo verisi");

  const student = page.getByTestId("fact-pricing.student_monthly");
  await expect(student).toContainText("Doğrulanmamış");
  await expect(student).toContainText("4.500 ₺ / ay");
  expect(await hasHorizontalScroll(page)).toBe(false);
});

test("A3: the owner verifies the student price and sees the new version in the history", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await openPricing(page);

  const student = page.getByTestId("fact-pricing.student_monthly");
  await student.getByRole("button", { name: "Doğrula" }).click();
  await expect(student).toContainText("Doğrulandı");
  await expect(student.getByRole("button", { name: "Doğrula" })).toHaveCount(0);

  await student.getByRole("button", { name: "Geçmiş" }).click();
  const history = page.getByRole("dialog", { name: /Geçmiş: Öğrenci aylık üyelik/ });
  await expect(history).toContainText("Sürüm 2");
  await expect(history).toContainText("Sürüm 1");
  await expect(history).toContainText("Doğrulandı");
  await expect(history).toContainText("Oluşturuldu");
  await history.getByRole("button", { name: "Kapat" }).click();
  await expect(history).toHaveCount(0);
});

test("A4: the bio discrepancy is explained and rejected, and Home shows what is left", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await openKnowledge(page);
  await expect(page.getByRole("link", { name: /Öneriler/ })).toContainText("1 öneri sizi bekliyor");

  await page.getByRole("link", { name: /Öneriler/ }).click();
  const card = page.getByTestId("candidate-pricing.membership_monthly");
  await expect(card).toContainText(
    "Yapıştırdığınız metin 5.500 ₺ / ay diyor, ama doğrulanmış değeriniz 6.000 ₺ / ay.",
  );
  await expect(card).toContainText("Instagram bio: Aylık üyelik 5.500 TL");
  await card.getByRole("button", { name: "Mevcut değeri koru" }).click();
  await expect(page.getByText("İncelenecek öneri yok")).toBeVisible();

  await navLink(page, "Ana sayfa").click();
  await expect(page.getByTestId("readiness-level")).toHaveText("Taslaklar için hazır");
  await expect(page.locator('[data-requirement="account_connected"]')).toBeVisible();
  await expect(page.locator('[data-requirement="automation_reviewed"]')).toBeVisible();
  await expect(page.locator('[data-requirement="business_name"]')).toHaveCount(0); // done items are hidden
});

test("A5: a staff edit becomes a suggestion that contests the fact until the owner decides", async ({
  page,
}) => {
  // Staff proposes a new monthly price.
  await signInToWorkspace(page, STAFF, GYM);
  await openPricing(page);
  const monthly = page.getByTestId("fact-pricing.membership_monthly");
  await expect(monthly.getByRole("button", { name: "Doğrula" })).toHaveCount(0);
  await monthly.getByRole("button", { name: "Değişiklik öner" }).click();

  const editor = page.getByRole("dialog");
  const amount = editor.getByLabel("Tutar (TRY)");
  await amount.fill("7500");
  await expect(editor).toContainText("Müşteriler şunu görecek: 7.500 ₺");
  await editor.getByRole("button", { name: "Değer öner" }).click();
  await expect(editor.getByRole("status")).toContainText("öneri olarak gönderildi");
  await editor.getByRole("button", { name: "Kapat" }).first().click();

  // The verified value is unchanged but contested, so it is on hold.
  await expect(monthly).toContainText("6.000 ₺ / ay");
  await expect(monthly).toContainText("İtiraz var");

  // The owner sees who proposed what, and accepts it.
  await page.context().clearCookies();
  await signInToWorkspace(page, OWNER, GYM);
  await openKnowledge(page);
  await page.getByRole("link", { name: /Öneriler/ }).click();
  // The seeded bio discrepancy and the staff proposal both concern the monthly price.
  await expect(page.getByTestId("candidate-pricing.membership_monthly")).toHaveCount(2);
  const suggestion = page
    .getByTestId("candidate-pricing.membership_monthly")
    .filter({ hasText: "Demo Personel" });
  await expect(suggestion).toContainText("Demo Personel 7.500 ₺ / ay değerini öneriyor (mevcut değer: 6.000 ₺ / ay).");
  await suggestion.getByRole("button", { name: "7.500 ₺ / ay değerini kullan" }).click();

  await page.getByRole("link", { name: "İşletme bilgilerine dön" }).click();
  await page.getByRole("link", { name: /Fiyatlar/ }).click();
  const updated = page.getByTestId("fact-pricing.membership_monthly");
  await expect(updated).toContainText("7.500 ₺ / ay");
  await expect(updated).toContainText("Doğrulandı");
  await expect(updated).not.toContainText("İtiraz var");
});
