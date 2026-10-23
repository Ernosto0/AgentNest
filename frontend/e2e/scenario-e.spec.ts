import { expect, test, type Page } from "@playwright/test";
import {
  API,
  dailyReport,
  expectNoHorizontalScroll,
  metricValue,
  openMore,
  ownerSetup,
  reseedDemo,
  say,
  signInToWorkspace,
  simulateMessage,
  type ReportMetric,
} from "./helpers";

// Scenario E: review the day (docs/product/acceptance-criteria.md AC-E3, AC-E4, AC-E5, AC-X2).
// Two customer messages arrive today through the signed-webhook path of the simulator; the
// seeded history (H16) is yesterday's. Every number on the report opens a list with that many
// rows, the SİMÜLASYON label is on the report, and the activity feed shows the same events.

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

test.setTimeout(180_000); // Includes seeding and tapping every nonzero metric in mobile WebKit.

test.beforeEach(() => {
  reseedDemo();
});

/** The Turkish label of each metric the report can show (frontend/src/i18n/locales/tr/reports.json). */
const LABEL: Record<string, string> = {
  inbound_messages: "Gelen mesaj",
  conversations_with_inbound: "Yeni mesaj gelen konuşma",
  new_conversations: "Yeni konuşma",
  replies_sent: "Gönderilen yanıt",
  replies_sent_approved: "Onayla gönderilen yanıt",
  escalations: "Size yönlendirilen konuşma",
  content_published: "Yayımlanan gönderi",
  content_failed: "Yayımlanamayan gönderi",
  integration_errors: "Bağlantı hatası",
};

/** Rows of the open drill-down, after loading every page. */
async function drillDownRows(page: Page): Promise<number> {
  const more = page.getByRole("button", { name: "Daha fazla göster" });
  while (await more.isVisible().catch(() => false)) {
    const before = await page.getByTestId("metric-item").count();
    await more.click();
    await expect.poll(() => page.getByTestId("metric-item").count()).toBeGreaterThan(before);
  }
  return page.getByTestId("metric-item").count();
}

/** Every nonzero metric must have a link and expose the records behind its value (AC-E3). */
async function checkDrillDowns(page: Page, metrics: ReportMetric[]): Promise<number> {
  const nonzero = metrics.filter((metric) => (metric.value ?? 0) !== 0);
  for (const metric of nonzero) {
    expect(metric.link.route, `${metric.key} has a drill-down`).toBeTruthy();
    const link = page.locator(`main a[href="${metric.link.route}"]`);
    await expect(link, metric.key).toHaveCount(1);
    await link.click();
    await expect(page.getByTestId("metric-count"), metric.key).toBeVisible();
    const rows = await drillDownRows(page);
    if (metric.key === "median_first_response_minutes") {
      // A median is a duration, not a count: its list has one row per answered burst.
      expect(rows, metric.key).toBeGreaterThan(0);
    } else {
      expect(rows, `${metric.key} = ${metric.value}`).toBe(metric.value);
      await expect(page.getByTestId("metric-count")).toHaveText(`Toplam: ${metric.value}`);
    }
    await expectNoHorizontalScroll(page, `drill-down ${metric.key}`);
    await page.getByRole("link", { name: "Rapora dön", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Günlük rapor", level: 1 })).toBeVisible();
  }
  return nonzero.length;
}

test("E: the command answer equals the report; every number opens a list of that size", async ({
  page,
  request,
}, testInfo) => {
  const { csrf, workspaceId } = await ownerSetup(request);
  await simulateMessage(request, csrf, workspaceId, "price");
  await simulateMessage(request, csrf, workspaceId, "hours");
  // The worker turns the webhook events into messages: wait until both are counted.
  await expect
    .poll(async () => metricValue(await dailyReport(request, workspaceId), "inbound_messages"), {
      timeout: 30_000,
    })
    .toBe(2);

  await signInToWorkspace(page, OWNER, GYM);
  await say(page, "Bugün kaç DM geldi?");
  const answer = page.getByTestId("command-result");
  await expect(answer).toContainText("gelen mesaj:", { timeout: 15_000 });
  const asked = Number(/gelen mesaj: (\d+)/.exec(await answer.innerText())![1]);
  const report = await dailyReport(request, workspaceId);
  expect(asked).toBe(metricValue(report, "inbound_messages")); // AC-E4 in the browser
  expect(asked).toBe(2);
  await expect(answer.getByTestId("simulated-badge")).toBeVisible();

  // The answer links to the report.
  await answer.getByRole("link", { name: "Raporu aç" }).click();
  await expect(page.getByRole("heading", { name: "Günlük rapor", level: 1 })).toBeVisible();
  // AC-E5: the report over simulated records says so.
  expect(report.has_simulated_data).toBe(true);
  await expect(page.getByRole("main").getByTestId("simulated-badge").first()).toBeVisible();
  await expectNoHorizontalScroll(page, "report");

  // AC-E3: every nonzero number is a link; its list has exactly that many rows.
  const checked = await checkDrillDowns(page, report.metrics);
  expect(checked).toBeGreaterThanOrEqual(5);
  testInfo.annotations.push({ type: "drill-downs checked", description: String(checked) });

  // The activity feed shows the same two events (the messages group).
  await openMore(page, "Etkinlik");
  await expect(page.getByRole("heading", { name: "Etkinlik", level: 1 })).toBeVisible();
  await expect(page.getByTestId("simulated-badge").first()).toBeVisible();
  await page.getByRole("button", { name: "Mesajlar" }).click();
  const received = page.getByTestId("activity-entry").filter({ hasText: "Mesaj alındı" });
  await expect(received.first()).toBeVisible({ timeout: 15_000 }); // the feed loads after the click
  const today = report.local_date;
  const api = await request.get(
    `${API}/api/v1/workspaces/${workspaceId}/activity?type=messages&date=${today}&limit=100`,
  );
  expect(api.ok()).toBe(true);
  const todays = (await api.json()).items.filter((e: { action: string }) => e.action === "message.received");
  expect(todays).toHaveLength(2);
  await expect(received.first().getByTestId("simulated-badge")).toBeVisible();
  await expectNoHorizontalScroll(page, "activity");
});

test("E: yesterday's seeded report has the H16 numbers, each opening its list", async ({
  page,
  request,
}) => {
  const { workspaceId } = await ownerSetup(request);
  await signInToWorkspace(page, OWNER, GYM);
  await openMore(page, "Günlük rapor");
  await page.getByRole("button", { name: "Önceki gün" }).click();
  await expect(page.getByRole("button", { name: "Bugüne dön" })).toBeVisible();
  const url = new URL(page.url());
  const date = url.searchParams.get("date")!;
  expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);

  // H16: 6 messages in 6 new conversations, 4 replies (all approved), 1 handed to a person,
  // 1 post published and 1 failed with 1 integration error.
  const expected: Record<string, number> = {
    inbound_messages: 6,
    conversations_with_inbound: 6,
    new_conversations: 6,
    replies_sent: 4,
    replies_sent_approved: 4,
    escalations: 1,
    content_published: 1,
    content_failed: 1,
    integration_errors: 1,
  };
  const report = await dailyReport(request, workspaceId, date);
  expect(report.has_simulated_data).toBe(true);
  for (const [key, value] of Object.entries(expected)) {
    expect(metricValue(report, key), key).toBe(value);
    await expect(page.getByRole("link", { name: `${LABEL[key]}: ${value}`, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("main").getByTestId("simulated-badge").first()).toBeVisible();

  await checkDrillDowns(page, report.metrics);
});

test("E: historical links stay on their snapshot after state changes and regeneration", async ({ page, request }) => {
  const { csrf, workspaceId } = await ownerSetup(request);
  await signInToWorkspace(page, OWNER, GYM);
  await openMore(page, "Günlük rapor");
  await page.getByRole("button", { name: "Önceki gün" }).click();
  await expect(page.getByRole("button", { name: "Bugüne dön" })).toBeVisible();
  const date = new URL(page.url()).searchParams.get("date")!;
  const saved = await dailyReport(request, workspaceId, date);
  const attention = saved.metrics.find((m) => m.key === "attention_now")!;
  expect(attention.value).toBeGreaterThan(0);
  const originalSnapshot = new URL(attention.link.api!, API).searchParams.get("snapshot_id");
  expect(originalSnapshot).toBeTruthy();

  // Yesterday's pending approval may already have expired, so measure today's baseline.
  const before = metricValue(await dailyReport(request, workspaceId), "attention_now");
  for (const alias of ["Snapshot customer one", "Snapshot customer two"]) {
    const simulated = await request.post(`${API}/api/v1/dev/workspaces/${workspaceId}/simulate/customer-message`, {
      data: { customer_alias: alias, text: "Bu bir rezalet, çok memnuniyetsizim." },
      headers: { "X-CSRF-Token": csrf },
    });
    expect(simulated.ok()).toBe(true);
  }
  await expect.poll(async () => metricValue(await dailyReport(request, workspaceId), "attention_now"), {
    timeout: 30_000,
  }).toBe(before + 2);
  expect(before + 2).toBeGreaterThan(attention.value!);
  const generated = await request.post(`${API}/api/v1/workspaces/${workspaceId}/reports/daily/generate`, {
    data: { date }, headers: { "X-CSRF-Token": csrf },
  });
  expect(generated.ok()).toBe(true);
  const latest = await generated.json();
  expect(latest.snapshot_id).not.toBe(originalSnapshot);
  expect(metricValue(latest, "attention_now")).toBeGreaterThan(attention.value!);

  await page.locator(`main a[href="${attention.link.route}"]`).click();
  await expect(page.getByTestId("metric-count")).toHaveText(`Toplam: ${attention.value}`);
  expect(await drillDownRows(page)).toBe(attention.value);
  const back = page.getByRole("link", { name: "Rapora dön", exact: true });
  await expect(back).toHaveAttribute("href", `/w/${workspaceId}/more/reports?date=${date}&snapshot_id=${originalSnapshot}`);
  await back.click();
  await expect(page.getByRole("heading", { name: "Günlük rapor", level: 1 })).toBeVisible();
  await expect(page.locator(`main a[href="${attention.link.route}"]`)).toHaveText(String(attention.value));
});
