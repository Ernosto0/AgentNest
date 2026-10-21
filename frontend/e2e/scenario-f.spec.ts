import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  SEEDED_PUBLISHED_POSTS,
  addFailureRule,
  apiLogin,
  localFields,
  ownContentCards,
  reseedDemo,
  runDueJobs,
  signInToWorkspace,
  simulatorPublished,
  statusBadge,
  submitFeedPost,
} from "./helpers";

// Scenario F: publishing goes wrong in the simulated Instagram (docs/product/acceptance-criteria.md
// AC-F6, AC-F7; INV-18). The failure is scripted through the dev API; the dev "run due jobs" API
// moves the queue along. Waiting minutes for the slow retry and reconcile paths is not done here:
// those are proven by the integration tests (tests/integration/content/test_publish_*.py).

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;
const GYM_NAME = "Gölkent Fitness & Pilates";

test.beforeEach(() => {
  reseedDemo();
});

interface Setup {
  csrf: string;
  workspaceId: string;
}

async function setup(request: APIRequestContext): Promise<Setup> {
  const { csrf, memberships } = await apiLogin(request, OWNER);
  const gym = memberships.find((m) => m.workspace_name === GYM_NAME);
  expect(gym).toBeDefined();
  return { csrf, workspaceId: gym!.workspace_id };
}

test("F6: invalid media fails at once, says why, and offers to edit and send again", async ({
  page,
  request,
}) => {
  const env = await setup(request);
  await addFailureRule(request, env.csrf, env.workspaceId, "publish", "invalid_media", 1);
  const contentId = await submitFeedPost(request, env);

  await signInToWorkspace(page, OWNER, GYM);
  await page.goto(`/w/${env.workspaceId}/content/${contentId}`);
  await runDueJobs(request, env.csrf);

  // Başarısız, never "Yayınlandı" (INV-18), with the cause in plain language and the next step.
  await expect(statusBadge(page)).toHaveAttribute("data-status", "failed", { timeout: 60_000 });
  await expect(statusBadge(page)).toContainText("Başarısız");
  const detail = page.getByTestId("failure-detail");
  await expect(detail).toHaveAttribute("data-code", "MEDIA_REJECTED");
  await expect(detail).toContainText("Instagram görseli işleyemedi.");
  await expect(detail).toContainText("Başka bir görsel seçip gönderiyi yeniden zamanlayın.");
  await expect(page.getByTestId("failure-final")).toContainText("Otomatik olarak tekrar denenmeyecek.");
  await expect(page.getByText("Yayınlandı")).toHaveCount(0);

  // The way forward: edit and send again takes the owner to the editor.
  await detail.getByRole("button", { name: "Düzenle ve yeniden gönder" }).click();
  await expect(page.getByLabel("Başlık")).toBeFocused();

  // Nothing reached the simulated Instagram.
  expect(await simulatorPublished(request, env.workspaceId)).toHaveLength(SEEDED_PUBLISHED_POSTS);

  // The failed post is listed under Sorunlar, with its badge (the seeded failed post is left out).
  await page.getByRole("link", { name: "← İçerik" }).click();
  await page.getByRole("tab", { name: "Sorunlar" }).click();
  await expect(ownContentCards(page).locator("[data-status]")).toHaveAttribute(
    "data-status",
    "failed",
  );
});

test("F7: a transient error shows when it will be tried again (Tekrar denenecek HH:MM)", async ({
  page,
  request,
}) => {
  const env = await setup(request);
  await addFailureRule(request, env.csrf, env.workspaceId, "publish", "transient", 1);
  const contentId = await submitFeedPost(request, env);

  await signInToWorkspace(page, OWNER, GYM);
  await page.goto(`/w/${env.workspaceId}/content/${contentId}`);
  await runDueJobs(request, env.csrf);

  await expect(statusBadge(page)).toHaveAttribute("data-status", "retry_scheduled", { timeout: 60_000 });
  const label = (await statusBadge(page).innerText()).trim();
  const match = /^Tekrar denenecek (\d{2}):(\d{2})$/.exec(label);
  expect(match, `badge reads "${label}"`).not.toBeNull();

  // The time is the next attempt, about a minute away (first backoff step), in the workspace zone.
  const now = localFields(0).time.split(":").map(Number) as [number, number];
  const shown = [Number(match![1]), Number(match![2])] as const;
  const ahead = (shown[0] * 60 + shown[1] - (now[0] * 60 + now[1]) + 1440) % 1440;
  expect(ahead).toBeLessThanOrEqual(3);

  const retry = page.getByTestId("failure-retry");
  await expect(retry).toContainText(`Tekrar denenecek: ${match![1]}:${match![2]}`);
  await expect(retry).toContainText("1. deneme yapıldı");
  await expect(page.getByTestId("failure-detail")).toContainText("Otomatik olarak yeniden denenecek.");
  await expect(page.getByText("Yayınlandı")).toHaveCount(0);

  // Still in the "Zamanlanan" tab, with the same time, and nothing has been published.
  await page.getByRole("link", { name: "← İçerik" }).click();
  await page.getByRole("tab", { name: "Zamanlanan" }).click();
  const card = page.getByTestId("content-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText(`Tekrar denenecek ${match![1]}:${match![2]}`);
  expect(await simulatorPublished(request, env.workspaceId)).toHaveLength(SEEDED_PUBLISHED_POSTS);
});
