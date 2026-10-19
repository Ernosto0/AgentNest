import { expect, test, type Page } from "@playwright/test";
import { hasHorizontalScroll, navLink, reseedDemo, signInToWorkspace } from "./helpers";

// Scenario C: natural-language commands (docs/product/acceptance-criteria.md AC-C1, AC-C2, AC-C6)
// and paste-and-extract (AC-A6). The fake AI is deterministic; the worker runs the jobs.

const OWNER = "owner@demo.local";
const STAFF = "staff@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

test.beforeEach(() => {
  reseedDemo(); // the commands below change facts; every test starts from the same data
});

async function say(page: Page, text: string) {
  await page.getByLabel("Komut").fill(text);
  await page.getByRole("button", { name: "Gönder" }).click();
}

async function openPricing(page: Page) {
  await navLink(page, "Daha fazla").click();
  // Exact: a command result may also show an "İşletme bilgilerini aç" link.
  await page.getByRole("link", { name: "İşletme bilgileri", exact: true }).click();
  await page.getByRole("link", { name: /Fiyatlar/ }).click();
  await expect(page.getByRole("heading", { name: "Fiyatlar", level: 1 })).toBeVisible();
}

test("C1/C2: a price command is confirmed and becomes a new fact version with its source", async ({
  page,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await expect(page.getByTestId("ai-mode")).toHaveText("Çevrimdışı demo yapay zekâsı");
  expect(await hasHorizontalScroll(page)).toBe(false);

  await say(page, "Aylık üyelik artık 7.000 TL");
  const card = page.getByTestId("confirmation-card");
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card.getByTestId("change-from")).toHaveText("6.000 ₺ / ay");
  await expect(card.getByTestId("change-to")).toHaveText("7.000 ₺ / ay");
  expect(await hasHorizontalScroll(page)).toBe(false);

  await card.getByRole("button", { name: "Onayla" }).click();
  const result = page.getByTestId("command-result");
  await expect(result).toContainText("Aylık üyelik güncellendi: 6.000 ₺ / ay → 7.000 ₺ / ay (sürüm 2).", {
    timeout: 15_000,
  });

  await openPricing(page);
  const monthly = page.getByTestId("fact-pricing.membership_monthly");
  await expect(monthly).toContainText("7.000 ₺ / ay");
  await expect(monthly).toContainText("Sohbet komutu"); // the source of the current version
  await monthly.getByRole("button", { name: "Geçmiş" }).click();
  const history = page.getByRole("dialog", { name: /Geçmiş: Aylık üyelik/ });
  await expect(history).toContainText("Sürüm 2");
  await expect(history).toContainText("Sürüm 1");
  await expect(history).toContainText("6.000 ₺ / ay"); // the previous value is preserved
});

test("C6: an ambiguous price asks which one, then confirms; withdrawing changes nothing", async ({
  page,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await say(page, "fiyat artık 7000");

  const chips = page.getByTestId("clarification");
  await expect(chips).toBeVisible({ timeout: 15_000 });
  await expect(chips).toContainText("“7000” hangi bilgi için?");
  await expect(chips.getByRole("button", { name: /^Aylık üyelik/ })).toBeVisible();
  await expect(chips.getByRole("button", { name: /^3 aylık üyelik/ })).toBeVisible();
  await expect(chips.getByRole("button", { name: /^Reformer 8 seans/ })).toBeVisible();
  await expect(chips.getByRole("button", { name: /Öğrenci/ })).toHaveCount(0); // not verified

  await chips.getByRole("button", { name: /^3 aylık üyelik/ }).click();
  const card = page.getByTestId("confirmation-card");
  await expect(card.getByTestId("change-from")).toHaveText("16.500 ₺ / paket");
  await expect(card.getByTestId("change-to")).toHaveText("7.000 ₺ / paket");
  await card.getByRole("button", { name: "Vazgeç" }).click();
  await expect(page.getByTestId("command-result")).toContainText("İptal edildi. Hiçbir şey değişmedi.");

  await openPricing(page);
  await expect(page.getByTestId("fact-pricing.membership_3_months")).toContainText("16.500 ₺ / paket");
});

test("a request to publish is refused with a pointer to Content and nothing to approve", async ({
  page,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await say(page, "gönderiyi şimdi yayınla");

  const result = page.getByTestId("command-result");
  await expect(result).toContainText("Bunu henüz yapamıyorum", { timeout: 15_000 });
  await expect(result.getByRole("link", { name: "İçeriğe git" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Onayla" })).toHaveCount(0);

  await result.getByRole("link", { name: "İçeriğe git" }).click();
  await expect(page.getByRole("heading", { name: "İçerik", level: 1 })).toBeVisible();
});

test("a question is answered from the verified fact", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await say(page, "Aylık üyelik ne kadar?");
  await expect(page.getByTestId("command-result")).toContainText("Aylık üyelik: 6.000 ₺ / ay", {
    timeout: 15_000,
  });
});

test("the approvals tab shows a pending confirmation and decides it", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await say(page, "Aylık üyelik artık 7.500 TL");
  await expect(page.getByTestId("confirmation-card")).toBeVisible({ timeout: 15_000 });

  await navLink(page, "Onaylar").click();
  await expect(page.getByRole("heading", { name: "Onaylar", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /Bilgi güncelleme/ }).click();
  const detail = page.getByTestId("approval-detail");
  await expect(detail.getByTestId("change-to")).toHaveText("7.500 ₺ / ay");
  // The decision buttons are in the sheet's footer, next to (not inside) the details.
  await page.getByRole("dialog").getByRole("button", { name: "Onayla" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await openPricing(page);
  await expect(page.getByTestId("fact-pricing.membership_monthly")).toContainText("7.500 ₺ / ay");
});

test("a staff confirmation becomes a suggestion for the owner, not a change", async ({ page }) => {
  await signInToWorkspace(page, STAFF, GYM);
  await say(page, "Aylık üyelik artık 7.500 TL");
  const card = page.getByTestId("confirmation-card");
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card).toContainText("bir öneri olarak sahibe iletilir");
  await card.getByRole("button", { name: "Onayla" }).click();
  await expect(page.getByTestId("command-result")).toContainText("önerisi sahibe iletildi", {
    timeout: 15_000,
  });

  await openPricing(page);
  await expect(page.getByTestId("fact-pricing.membership_monthly")).toContainText("6.000 ₺ / ay");
});

test("A6: pasted text yields suggestions with excerpts and changes no fact", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "İşletme bilgileri", exact: true }).click();

  await page.getByTestId("open-paste-extract").click();
  await page
    .getByLabel("Yapıştırılan metin")
    .fill("Gölkent Fitness 💪\nAylık üyelik 6.500 TL\nTel: 0555 123 45 67");
  await page.getByRole("button", { name: "Önerileri bul" }).click();
  await expect(page.getByTestId("extract-result")).toContainText("2 öneri bulundu", {
    timeout: 20_000,
  });
  await page.getByRole("link", { name: "Önerilere git" }).click();

  const price = page
    .getByTestId("candidate-pricing.membership_monthly")
    .filter({ hasText: "Aylık üyelik 6.500 TL" });
  await expect(price).toContainText("6.500 ₺ / ay");
  await expect(page.getByTestId("candidate-contact.phone")).toContainText("Tel: 0555 123 45 67");

  await page.getByRole("link", { name: "İşletme bilgilerine dön" }).click();
  await page.getByRole("link", { name: /Fiyatlar/ }).click();
  await expect(page.getByTestId("fact-pricing.membership_monthly")).toContainText("6.000 ₺ / ay"); // unchanged
});
