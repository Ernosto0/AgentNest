import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import {
  chooseLanguage,
  expectNoHorizontalScroll,
  navLink,
  ownerSetup,
  reseedDemo,
  resetLocale,
  signInToWorkspace,
} from "./helpers";

// AC-X3: switching the language changes every visible string on the main screens. The catalogs
// have the same keys (npm run i18n:check); this spec proves that the screens use them: known
// strings per screen in Turkish, then in English after the switch in Settings, then Turkish
// again, and no raw catalog key ("home.title") or unfilled "{{placeholder}}" is ever on screen.

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

// The first segment of every catalog key: a visible "<namespace>.<something>" is a raw key.
const localesDir = fileURLToPath(new URL("../src/i18n/locales/tr", import.meta.url));
const NAMESPACES = readdirSync(localesDir)
  .filter((file) => file.endsWith(".json"))
  .flatMap((file) => Object.keys(JSON.parse(readFileSync(`${localesDir}/${file}`, "utf8"))));
const RAW_KEY = new RegExp(`(?<![@\\w./-])(?:${NAMESPACES.join("|")})\\.[A-Za-z_][\\w.]*\\b`);

interface Strings {
  heading: string;
  text: string;
}
interface Screen {
  name: string;
  path: string;
  tr: Strings;
  en: Strings;
}

const SCREENS: Screen[] = [
  {
    name: "Home",
    path: "",
    tr: { heading: "Ana sayfa", text: "Sizi bekleyenler" },
    en: { heading: "Home", text: "Waiting for you" },
  },
  {
    name: "Inbox",
    path: "/inbox",
    tr: { heading: "Gelen kutusu", text: "Size gerek var" },
    en: { heading: "Inbox", text: "Needs you" },
  },
  {
    name: "Content",
    path: "/content",
    tr: { heading: "İçerik", text: "Zamanlanan" },
    en: { heading: "Content", text: "Scheduled" },
  },
  {
    name: "Approvals",
    path: "/approvals",
    tr: { heading: "Onaylar", text: "Hiçbir şey siz onaylamadan yapılmaz." },
    en: { heading: "Approvals", text: "Nothing happens without your approval." },
  },
  {
    name: "Knowledge",
    path: "/more/knowledge",
    tr: { heading: "İşletme bilgileri", text: "Doğrulanmamış hiçbir bilgi kullanılmaz." },
    en: { heading: "Business knowledge", text: "Nothing unverified is ever used." },
  },
  {
    name: "Reports",
    path: "/more/reports",
    tr: { heading: "Günlük rapor", text: "Her sayıya dokunursanız" },
    en: { heading: "Daily report", text: "Tap any number" },
  },
  {
    name: "Activity",
    path: "/more/activity",
    tr: { heading: "Etkinlik", text: "en yeniden eskiye" },
    en: { heading: "Activity", text: "newest first" },
  },
  {
    name: "Notifications",
    path: "/more/notifications",
    tr: { heading: "Bildirimler", text: "Okunmamış" },
    en: { heading: "Notifications", text: "Unread" },
  },
  {
    name: "Members",
    path: "/more/settings/members",
    tr: { heading: "Üyeler", text: "Üye davet et" },
    en: { heading: "Members", text: "Invite a member" },
  },
  {
    name: "Connections",
    path: "/more/settings/connections",
    tr: { heading: "Instagram bağlantısı", text: "Son hata" },
    en: { heading: "Instagram connection", text: "Last error" },
  },
  {
    name: "System health",
    path: "/more/settings/system-health",
    tr: { heading: "Sistem durumu", text: "Instagram hesapları" },
    en: { heading: "System health", text: "Instagram accounts" },
  },
];

test.beforeAll(() => {
  reseedDemo();
});

test.afterEach(async ({ request }) => {
  await resetLocale(request, OWNER); // the language is saved on the account
});

async function expectScreen(page: Page, screen: Screen, language: "tr" | "en", base: string) {
  const strings = screen[language];
  await page.goto(`${base}${screen.path}`);
  await expect(page.getByRole("heading", { name: strings.heading, level: 1, exact: true })).toBeVisible();
  await expect(page.getByText(strings.text).first()).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", language);
  await expect(page.getByText(/Yükleniyor|Loading/)).toHaveCount(0, { timeout: 15_000 });

  const visible = await page.locator("body").innerText();
  const raw = RAW_KEY.exec(visible);
  expect(raw, `${screen.name} (${language}) shows a raw key: ${raw?.[0]}`).toBeNull();
  expect(visible, `${screen.name} (${language}) shows an unfilled placeholder`).not.toContain("{{");
  // The other language's heading must be gone: nothing is left untranslated.
  const other = language === "tr" ? screen.en : screen.tr;
  if (other.heading !== strings.heading) {
    await expect(page.getByRole("heading", { name: other.heading, level: 1, exact: true })).toHaveCount(0);
  }
  await expectNoHorizontalScroll(page, `${screen.name} (${language})`);
}

test("X3: tr to en to tr on every main screen, with no raw keys on screen", async ({ page, request }) => {
  test.setTimeout(180_000);
  const { workspaceId } = await ownerSetup(request);
  const base = `/w/${workspaceId}`;
  await signInToWorkspace(page, OWNER, GYM);

  for (const screen of SCREENS) await expectScreen(page, screen, "tr", base);

  // The switch itself, in the Settings screen (the choice is saved on the account).
  await navLink(page, "Daha fazla").click();
  await page.getByRole("link", { name: "Ayarlar" }).click();
  await chooseLanguage(page, "English");
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await expect(navLink(page, "Inbox")).toBeVisible();

  for (const screen of SCREENS) await expectScreen(page, screen, "en", base);

  // And back: the Turkish strings return.
  await page.goto(`${base}/more/settings`);
  await chooseLanguage(page, "Türkçe");
  await expect(page.getByRole("heading", { name: "Dil" })).toBeVisible();
  await expect(navLink(page, "Gelen kutusu")).toBeVisible();
  await expectScreen(page, SCREENS[0]!, "tr", base);
});
