import { expect, test, type Page } from "@playwright/test";
import {
  IST,
  SAMPLE_STORY,
  SEEDED_PUBLISHED_POSTS,
  WEB,
  apiLogin,
  attachImage,
  localFields,
  navLink,
  openScheduleSheet,
  ownContentCards,
  reseedDemo,
  runDueJobs,
  say,
  signInToWorkspace,
  simulatorPublished,
  statusBadge,
  workspaceIds,
} from "./helpers";

// Scenario D: a story is prepared by command, gets its picture, is scheduled and published
// through the simulated Instagram (docs/product/acceptance-criteria.md AC-D1, AC-D2, AC-D4,
// AC-D5, AC-D6, AC-D8; INV-06, INV-18). Staff can only ask for approval. The fake AI is
// deterministic; the worker runs the jobs and the dev "run due jobs" API moves things along
// without waiting.

const OWNER = "owner@demo.local";
const STAFF = "staff@demo.local";
const GYM = /Gölkent Fitness & Pilates/;
const GYM_NAME = "Gölkent Fitness & Pilates";

test.beforeEach(() => {
  reseedDemo(); // every test starts from the same data (and no earlier post in the simulator)
});

/** "Deneme dersi için bir story hazırla" -> the draft opens with its overlay suggestions generated. */
async function storyDraftByCommand(page: Page) {
  await say(page, "Deneme dersi için bir story hazırla");
  const open = page.getByTestId("command-result").getByRole("link", { name: "İçeriği aç" });
  await expect(open).toBeVisible({ timeout: 15_000 });
  await open.click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByTestId("generation-running")).toHaveCount(0, { timeout: 30_000 });
  // A story has overlay suggestions and a note that the text belongs on the picture; no caption.
  await expect(page.getByTestId("overlay-note")).toContainText("metin görselin üzerinde olmalı");
  await expect(page.getByRole("textbox", { name: "Öneri 1", exact: true })).not.toHaveValue("");
  await expect(page.getByLabel("Açıklama", { exact: true })).toHaveCount(0);
}

/** The story with its picture attached, ready to be scheduled. */
async function storyDraftWithImage(page: Page) {
  await storyDraftByCommand(page);
  await attachImage(page, SAMPLE_STORY);
}

test("D1/D2/D4: a story by command, an uploaded picture, scheduled +2 minutes shows Zamanlandı", async ({
  page,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await storyDraftWithImage(page);
  await expect(statusBadge(page)).toHaveAttribute("data-status", "draft");

  const sheet = await openScheduleSheet(page);
  // The owner may publish now; the time is in the workspace's own zone.
  await expect(sheet.getByLabel("Hemen yayınla")).toBeVisible();
  await expect(sheet.getByTestId("timezone-label")).toHaveText("İstanbul saati");
  const when = localFields(2);
  await sheet.getByLabel("Tarih").fill(when.date);
  await sheet.getByLabel("Saat", { exact: true }).fill(when.time);
  await expect(sheet.getByTestId("summary-when")).toContainText("İstanbul saati");
  await expect(sheet.getByTestId("summary-account")).toContainText("SİMÜLASYON");
  await sheet.getByRole("button", { name: "Onayla ve zamanla" }).click();
  await expect(sheet).toHaveCount(0);

  // Zamanlandı, with the time; nothing is "published" yet (INV-18).
  await expect(statusBadge(page)).toHaveAttribute("data-status", "scheduled");
  await expect(statusBadge(page)).toContainText("Zamanlandı");
  await expect(page.getByTestId("status-panel")).toContainText("Yayın zamanı:");
  await expect(page.getByText("Yayınlandı")).toHaveCount(0);

  await navLink(page, "İçerik").click();
  await page.getByRole("tab", { name: "Zamanlanan" }).click();
  const card = page.getByTestId("content-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("Zamanlandı");
  await expect(card).toContainText("Zamanlanan: ");
  await expect(card).toContainText(when.time); // the local time of the schedule, 24 h clock
  await expect(card.getByTestId("simulated-badge")).toBeVisible();
});

test("D5/INV-06/INV-18: Hemen yayınla publishes once and reads Yayınlandı with SİMÜLASYON", async ({
  page,
  request,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await storyDraftWithImage(page);

  const sheet = await openScheduleSheet(page);
  await sheet.getByLabel("Hemen yayınla").check();
  await expect(sheet.getByTestId("summary-when")).toContainText("Hemen");
  await sheet.getByRole("button", { name: "Onayla ve hemen yayınla" }).click();
  await expect(sheet).toHaveCount(0);

  // Not "Yayınlandı" until the provider confirmed it (the container takes a moment to be ready).
  await expect(statusBadge(page)).not.toHaveAttribute("data-status", "published");

  // Move the queue along ourselves: the worker may already have it, then nothing is due.
  const { csrf } = await apiLogin(request, OWNER);
  await runDueJobs(request, csrf);

  await expect(statusBadge(page)).toHaveAttribute("data-status", "published", { timeout: 60_000 });
  await expect(statusBadge(page)).toContainText("Yayınlandı");
  await expect(page.getByTestId("simulated-badge").first()).toBeVisible();
  const permalink = page.getByTestId("permalink");
  await expect(permalink).toContainText("Gönderiyi aç");
  await expect(permalink.getByTestId("simulated-badge")).toBeVisible();

  // Exactly one post in the simulated Instagram (INV-06), and the item cannot be edited any more.
  const ids = await workspaceIds(request, OWNER);
  const published = await simulatorPublished(request, ids[GYM_NAME]!);
  expect(published).toHaveLength(SEEDED_PUBLISHED_POSTS + 1);
  expect(published.filter((post) => post.media_type === "STORIES")).toHaveLength(1);
  await expect(page.getByTestId("content-readonly")).toBeVisible();

  await navLink(page, "İçerik").click();
  await page.getByRole("tab", { name: "Yayınlanan" }).click();
  const card = ownContentCards(page);
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("Yayınlandı");
  await expect(card.getByTestId("simulated-badge")).toBeVisible();
});

test("D6: editing a scheduled story voids the approval and returns it to Taslak", async ({
  page,
  request,
}) => {
  await signInToWorkspace(page, OWNER, GYM);
  await storyDraftWithImage(page);

  const sheet = await openScheduleSheet(page);
  const when = localFields(180);
  await sheet.getByLabel("Tarih").fill(when.date);
  await sheet.getByLabel("Saat", { exact: true }).fill(when.time);
  await sheet.getByRole("button", { name: "Onayla ve zamanla" }).click();
  await expect(statusBadge(page)).toHaveAttribute("data-status", "scheduled");

  // The editor warns that an edit voids the approval, then does exactly that.
  await expect(page.getByTestId("voids-approval")).toBeVisible();
  await page.getByRole("textbox", { name: "Öneri 1", exact: true }).fill("Gelin, birlikte tanışalım!");
  await page.getByRole("button", { name: "Kaydet" }).click();
  await expect(statusBadge(page)).toHaveAttribute("data-status", "draft");
  await expect(statusBadge(page)).toContainText("Taslak");
  await expect(page.getByRole("button", { name: "Zamanla", exact: true })).toBeVisible();

  // Nothing is scheduled any more and nothing was published.
  await navLink(page, "İçerik").click();
  await page.getByRole("tab", { name: "Zamanlanan" }).click();
  await expect(page.getByText("Zamanlanmış içerik yok")).toBeVisible();
  const { csrf } = await apiLogin(request, OWNER);
  await runDueJobs(request, csrf);
  const ids = await workspaceIds(request, OWNER);
  expect(await simulatorPublished(request, ids[GYM_NAME]!)).toHaveLength(SEEDED_PUBLISHED_POSTS);
});

test("D8: staff cannot publish now; their submission reads Onay bekliyor", async ({ page }) => {
  await signInToWorkspace(page, STAFF, GYM);
  await storyDraftWithImage(page);

  const sheet = await openScheduleSheet(page);
  // There is no way to publish immediately for someone who cannot approve.
  await expect(sheet.getByLabel("Hemen yayınla")).toHaveCount(0);
  await expect(sheet.getByText("Hemen yayınla")).toHaveCount(0);
  await expect(sheet.getByRole("button", { name: "Onayla ve zamanla" })).toHaveCount(0);
  const soon = localFields(5);
  await sheet.getByLabel("Tarih").fill(soon.date);
  await sheet.getByLabel("Saat", { exact: true }).fill(soon.time);
  await expect(sheet.getByTestId("schedule-precheck")).toHaveAttribute(
    "data-code",
    "SCHEDULE_TOO_SOON_FOR_APPROVAL",
  );
  await expect(sheet.getByRole("button", { name: "Onaya gönder" })).toBeDisabled();

  const later = localFields(180);
  await sheet.getByLabel("Tarih").fill(later.date);
  await sheet.getByLabel("Saat", { exact: true }).fill(later.time);
  await sheet.getByRole("button", { name: "Onaya gönder" }).click();
  await expect(sheet).toHaveCount(0);

  await expect(statusBadge(page)).toHaveAttribute("data-status", "pending_approval");
  await expect(statusBadge(page)).toContainText("Onay bekliyor");
  await expect(page.getByTestId("status-panel")).toContainText(
    "Onay bekliyor: bir sahip ya da yönetici onaylayınca zamanlanır.",
  );
  await expect(page.getByText("Zamanlandı")).toHaveCount(0);
});

test("D8: the owner approves the staff submission and it becomes Zamanlandı", async ({
  page: staffPage,
  browser,
}) => {
  await signInToWorkspace(staffPage, STAFF, GYM);
  await storyDraftWithImage(staffPage);
  const sheet = await openScheduleSheet(staffPage);
  const later = localFields(180);
  await sheet.getByLabel("Tarih").fill(later.date);
  await sheet.getByLabel("Saat", { exact: true }).fill(later.time);
  await sheet.getByRole("button", { name: "Onaya gönder" }).click();
  await expect(statusBadge(staffPage)).toHaveAttribute("data-status", "pending_approval");

  // A second browser context: the owner has their own session, on the same viewport.
  const ownerContext = await browser.newContext({
    baseURL: WEB,
    locale: "tr-TR",
    timezoneId: IST,
    viewport: staffPage.viewportSize(),
  });
  const ownerPage = await ownerContext.newPage();
  await signInToWorkspace(ownerPage, OWNER, GYM);
  await navLink(ownerPage, "Onaylar").click();
  await ownerPage.getByRole("button", { name: /İçerik yayınlama/ }).first().click();
  const dialog = ownerPage.getByRole("dialog");
  await expect(dialog).toContainText("Bu onayla yayınlanacak içerik");
  await dialog.getByRole("button", { name: "Onayla" }).click();
  await expect(ownerPage.getByRole("dialog")).toHaveCount(0);

  await navLink(ownerPage, "İçerik").click();
  await ownerPage.getByRole("tab", { name: "Zamanlanan" }).click();
  await expect(ownerPage.getByTestId("content-card").locator("[data-status]")).toHaveAttribute(
    "data-status",
    "scheduled",
  );
});
