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
} from "./helpers";

// Scenario E: review the day (docs/product/acceptance-criteria.md AC-E3, AC-E4, AC-E5, AC-X2).
// Two customer messages arrive today through the signed-webhook path of the simulator; the
// seeded history (H16) is yesterday's. Every number on the report opens a list with that many
// rows, the SİMÜLASYON label is on the report, and the activity feed shows the same events.

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

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
    await more.click();
    await page.waitForTimeout(200); // the button re-renders while the next page loads
  }
  return page.getByTestId("metric-item").count();
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
  const reportUrl = page.url();
  const nonzero = report.metrics.filter((m) => (m.value ?? 0) !== 0 && m.link.route);
  expect(nonzero.length).toBeGreaterThanOrEqual(5);
  for (const metric of nonzero) {
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
    await page.goto(reportUrl);
    await expect(page.getByRole("heading", { name: "Günlük rapor", level: 1 })).toBeVisible();
  }
  testInfo.annotations.push({ type: "drill-downs checked", description: String(nonzero.length) });

  // The activity feed shows the same two events (the messages group).
  await openMore(page, "Etkinlik");
  await expect(page.getByRole("heading", { name: "Etkinlik", level: 1 })).toBeVisible();
  await expect(page.getByTestId("simulated-badge").first()).toBeVisible();
  await page.getByRole("button", { name: "Mesajlar" }).click();
  const received = page.getByTestId("activity-entry").filter({ hasText: "Mesaj alındı" });
  await expect(received.first()).toBeVisible();
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

  const reportUrl = page.url();
  for (const [key, value] of Object.entries(expected)) {
    await page.getByRole("link", { name: `${LABEL[key]}: ${value}`, exact: true }).click();
    await expect(page.getByTestId("metric-count")).toHaveText(`Toplam: ${value}`);
    expect(await drillDownRows(page), key).toBe(value);
    await page.goto(reportUrl);
    await expect(page.getByRole("heading", { name: "Günlük rapor", level: 1 })).toBeVisible();
  }
});
