import { expect, test } from "@playwright/test";
import {
  hasHorizontalScroll,
  loginViaUi,
  navLink,
  resetLocale,
  workspaceIds,
} from "./helpers";

const OWNER = "owner@demo.local";
const OTHER = "other@demo.local";

test.afterEach(async ({ request }) => {
  // Language is saved on the account: put the demo users back to Turkish for the next test.
  await resetLocale(request, OWNER);
  await resetLocale(request, OTHER);
});

test("owner: Turkish shell with simulation banner, English switch, workspace switch, sign out", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await loginViaUi(page, OWNER);

  // Workspace picker, then into Gölkent Fitness.
  await expect(page.getByRole("heading", { name: "Çalışma alanı seçin" })).toBeVisible();
  await page.getByRole("link", { name: /Gölkent Fitness & Pilates/ }).click();

  // Home shell in Turkish, with the simulation banner.
  await expect(page.getByRole("heading", { name: "Ana sayfa", level: 1 })).toBeVisible();
  const banner = page.getByTestId("simulation-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Demo çalışma alanı — simülasyon");
  for (const label of ["Ana sayfa", "Gelen kutusu", "İçerik", "Onaylar", "Daha fazla"]) {
    await expect(navLink(page, label)).toBeVisible();
  }
  await expect(page.locator("html")).toHaveAttribute("lang", "tr");

  // More → Settings → Language → English: the strings change.
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "Ayarlar" }).click();
  await expect(page.getByRole("heading", { name: "Dil" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await expect(banner).toContainText("Demo workspace — simulation");
  await expect(navLink(page, "Inbox")).toBeVisible();
  await expect(navLink(page, "Gelen kutusu")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  // The choice is saved on the account: it survives a reload.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();

  // Switch to the other demo workspace (still a demo: the banner stays).
  await page.getByLabel("Workspace").selectOption({ label: "Harbor Pilates Studio" });
  await expect(page.getByLabel("Workspace").locator("option:checked")).toHaveText(
    "Harbor Pilates Studio",
  );
  await navLink(page, "Home").click();
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await expect(page.getByRole("main").getByText("Harbor Pilates Studio")).toBeVisible();
  await expect(banner).toBeVisible();

  // Sign out.
  await navLink(page, "More").click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/); // the session is really gone
});

test("a wrong password shows a generic localised error and stays on the form", async ({ page }) => {
  await page.goto("/login");
  await loginViaUi(page, OWNER, "definitely-wrong-password");
  await expect(page.getByRole("alert")).toContainText("E-posta veya parola hatalı.");
  await expect(page).toHaveURL(/\/login$/);
});

test("a deep link asks for sign-in first and then returns to the page", async ({
  page,
  request,
}) => {
  const ids = await workspaceIds(request, OWNER);
  const golkent = ids["Gölkent Fitness & Pilates"];
  await page.goto(`/w/${golkent}/inbox`);
  await expect(page).toHaveURL(/\/login$/);
  await loginViaUi(page, OWNER);
  await expect(page).toHaveURL(new RegExp(`/w/${golkent}/inbox$`));
  await expect(page.getByRole("heading", { name: "Gelen kutusu", level: 1 })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Konuşmaları filtrele" })).toBeVisible();
});

test("tenant isolation: the other user lists only their workspace and gets 'not found' elsewhere", async ({
  page,
  request,
}) => {
  const ids = await workspaceIds(request, OWNER);
  await page.goto("/login");
  await loginViaUi(page, OTHER);

  // other@demo.local's account language is English, so the picker switches to English.
  await expect(page.getByRole("heading", { name: /Çalışma alanı seçin|Choose a workspace/ })).toBeVisible();
  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(1);
  await expect(items.first()).toContainText("Other Workspace");

  for (const name of ["Gölkent Fitness & Pilates", "Harbor Pilates Studio"]) {
    await page.goto(`/w/${ids[name]}`);
    await expect(page.getByRole("heading", { name: /Bulunamadı|Not found/ })).toBeVisible();
    await expect(page.getByTestId("simulation-banner")).toHaveCount(0);
  }
});

test("navigation adapts to the viewport: bottom tabs on phones, sidebar on desktop", async ({
  page,
}, testInfo) => {
  await page.goto("/login");
  await loginViaUi(page, OWNER);
  await page.getByRole("link", { name: /Gölkent Fitness & Pilates/ }).click();
  const nav = page.getByRole("navigation", { name: "Ana gezinme" });
  await expect(nav).toBeVisible();
  const box = await nav.boundingBox();
  const main = await page.getByRole("main").boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(main).not.toBeNull();
  expect(viewport).not.toBeNull();
  if (testInfo.project.name.startsWith("mobile")) {
    expect(box!.y + box!.height).toBeGreaterThanOrEqual(viewport!.height - 2); // pinned to the bottom
    expect(box!.width).toBeGreaterThanOrEqual(viewport!.width - 2);
    for (const link of await nav.getByRole("link").all()) {
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44); // touch target
    }
  } else {
    expect(box!.x + box!.width).toBeLessThanOrEqual(main!.x + 1); // sidebar sits left of the content
    expect(box!.height).toBeGreaterThan(200);
  }
});

test("every main screen fits a 360x740 phone without horizontal scroll, in both languages", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/login");
  expect(await hasHorizontalScroll(page)).toBe(false);
  await loginViaUi(page, OWNER);
  await expect(page.getByRole("heading", { name: "Çalışma alanı seçin" })).toBeVisible();
  expect(await hasHorizontalScroll(page)).toBe(false);

  await page.getByRole("link", { name: /Gölkent Fitness & Pilates/ }).click();
  const screens = {
    tr: ["Ana sayfa", "Gelen kutusu", "İçerik", "Onaylar", "Daha fazla"],
    en: ["Home", "Inbox", "Content", "Approvals", "More"],
  };
  for (const language of ["tr", "en"] as const) {
    if (language === "en") {
      await navLink(page, "Daha fazla").click();
      await page.getByRole("link", { name: "Ayarlar" }).click();
      await page.getByRole("button", { name: "English" }).click();
      await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
      expect(await hasHorizontalScroll(page), "en: settings").toBe(false);
    }
    for (const label of screens[language]) {
      await navLink(page, label).click();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(await hasHorizontalScroll(page), `${language}: ${label}`).toBe(false);
    }
  }
});
