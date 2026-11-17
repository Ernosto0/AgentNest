import { randomUUID } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { EMAIL_OUTBOX_DIR } from "./outbox";

/** The path of the verification link in the newest email sent to `email` (API mirrors them to disk). */
async function verificationPath(email: string): Promise<string> {
  let path = "";
  await expect(async () => {
    const mails = readdirSync(EMAIL_OUTBOX_DIR)
      .filter((name) => name.endsWith(".json"))
      .map((name) => JSON.parse(readFileSync(join(EMAIL_OUTBOX_DIR, name), "utf8")))
      .filter((mail) => mail.to_email === email)
      .sort((a, b) => String(a.sent_at).localeCompare(String(b.sent_at)));
    const match = /(\/verify-email\/\S+)/.exec(mails.at(-1)?.text_body ?? "");
    expect(match).not.toBeNull();
    path = match![1];
  }).toPass({ timeout: 15_000 });
  return path;
}

test("a new owner signs up, verifies the email and lands in the workspace wizard", async ({ page }) => {
  const email = `owner-${randomUUID().slice(0, 8)}@signup.example.test`;
  const password = "a-long-enough-password";

  await page.goto("/login");
  await page.getByRole("link", { name: "Hesap oluştur" }).click();
  await expect(page).toHaveURL(/\/signup$/);

  await page.getByLabel("Adınız").fill("Yeni Sahip");
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola").fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Hesap oluştur" }).click();
  await expect(page).toHaveURL(/\/check-email$/);
  await expect(page.getByRole("heading", { name: "E-postanızı kontrol edin" })).toBeVisible();

  // Before verifying, signing in only leads back to the "check your email" screen.
  await page.goto("/login");
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola").fill(password);
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page).toHaveURL(/\/check-email$/);
  await page.goto("/workspaces/new");
  await expect(page).toHaveURL(/\/check-email$/);

  // Open the emailed link: verifying needs a button press, then the session takes over.
  await page.goto(await verificationPath(email));
  await page.getByRole("button", { name: "E-postayı doğrula" }).click();
  await expect(page).toHaveURL(/\/workspaces\/new$/);
  await expect(page.getByRole("heading", { name: "Çalışma alanı oluştur" })).toBeVisible();
});
