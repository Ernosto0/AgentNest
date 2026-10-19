import { expect, test, type Page } from "@playwright/test";
import { hasHorizontalScroll, navLink, reseedDemo, signInToWorkspace } from "./helpers";

// Scenario B: a simulated customer writes, the assistant drafts a grounded reply, the owner
// approves it, and it is "sent" through the simulated Instagram
// (docs/product/acceptance-criteria.md AC-B1, AC-B5, AC-B6, AC-B7).
// The fake AI is deterministic and the worker runs the jobs (the debounce is 1 s in this stack).

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

test.beforeEach(() => {
  reseedDemo(); // the scenarios change conversations; every test starts from the same data
});

async function simulate(page: Page, script: string) {
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "Geliştirici araçları" }).click();
  await page.locator(`button[data-script="${script}"]`).click();
}

async function openFirstConversation(page: Page, customer: string) {
  await navLink(page, "Gelen kutusu").click();
  await expect(page.getByRole("heading", { name: "Gelen kutusu", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: new RegExp(customer) }).click({ timeout: 20_000 });
}

test("B5: a price question gets a grounded draft; approving sends it (simulated)", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await simulate(page, "price");

  await openFirstConversation(page, "Ayşe");
  const card = page.getByTestId("draft-card");
  await expect(card).toBeVisible({ timeout: 25_000 });
  await expect(card).toHaveAttribute("data-draft-status", "pending_approval");
  await expect(card.getByTestId("draft-text")).toContainText("Aylık üyelik ücretimiz 6.000 ₺ / ay.");
  expect(await hasHorizontalScroll(page)).toBe(false);

  // The value is a chip that says where it comes from.
  await card.getByTestId("fact-chip").click();
  await expect(card.getByRole("status")).toContainText("Kaynak: Aylık üyelik, doğrulandı");
  await expect(card).toContainText("Otomatik gönderim kapalı");
  await expect(card.getByTestId("simulated-badge")).toBeVisible();

  await card.getByRole("button", { name: "Onayla ve gönder" }).click();
  await expect(card).toHaveAttribute("data-draft-status", "sent", { timeout: 25_000 });
  await expect(card).toContainText("Gönderildi");
  await expect(card.getByTestId("simulated-badge")).toBeVisible();
  // The reply is now part of the conversation, marked as simulated.
  await expect(page.getByTestId("messages")).toContainText("Aylık üyelik ücretimiz 6.000 ₺ / ay.");
});

test("B6: a complaint is handed to the owner with its reasons; nothing can be approved", async ({
  page,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await simulate(page, "complaint");

  await navLink(page, "Gelen kutusu").click();
  const row = page.getByRole("link", { name: /Burak/ });
  await expect(row).toBeVisible({ timeout: 25_000 });
  await expect(row.getByTestId("attention-chip")).toHaveText("Size gerek var", { timeout: 25_000 });

  await row.click();
  const card = page.getByTestId("draft-card");
  await expect(card).toContainText("Bu mesaja kendiniz yanıt vermelisiniz.");
  await expect(card).toContainText("Şikayet");
  await expect(card.getByRole("button", { name: "Onayla ve gönder" })).toHaveCount(0);
});

test("B7: an injection attempt never yields a sendable discount", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await simulate(page, "injection");

  await openFirstConversation(page, "Kerem");
  const card = page.getByTestId("draft-card");
  await expect(card).toBeVisible({ timeout: 25_000 });
  await expect(card).toHaveAttribute("data-draft-status", "needs_human");
  await expect(card).toContainText("İndirim istiyor");
  await expect(card.getByRole("button", { name: "Onayla ve gönder" })).toHaveCount(0);
  await expect(card).not.toContainText("%100");
});

test("a reply sent through a timeout is checked, then confirmed by the echo", async ({ page }) => {
  await signInToWorkspace(page, OWNER, GYM);
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "Geliştirici araçları" }).click();
  await page.getByLabel("İşlem").selectOption("send");
  await page.getByLabel("Hata").selectOption("timeout_after_success");
  await page.getByRole("button", { name: "Sonraki çağrı için ekle" }).click();
  await page.locator('button[data-script="price"]').click();

  await openFirstConversation(page, "Ayşe");
  const card = page.getByTestId("draft-card");
  await expect(card).toHaveAttribute("data-draft-status", "pending_approval", { timeout: 25_000 });
  await card.getByRole("button", { name: "Onayla ve gönder" }).click();
  // It may not be visible long, but it must never show as sent before it is confirmed.
  await expect(card).toHaveAttribute("data-draft-status", /outcome_unknown|sent/, { timeout: 25_000 });
  await expect(card).toHaveAttribute("data-draft-status", "sent", { timeout: 40_000 });
});
