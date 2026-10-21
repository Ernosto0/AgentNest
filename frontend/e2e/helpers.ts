import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "demo-password";
export const API = `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`;

export interface Membership {
  workspace_id: string;
  workspace_name: string;
  role: string;
  is_demo: boolean;
}

/** Sign in through the API (no UI) and return the CSRF token and memberships. */
export async function apiLogin(
  request: APIRequestContext,
  email: string,
): Promise<{ csrf: string; memberships: Membership[] }> {
  const login = await request.post(`${API}/api/v1/auth/login`, {
    data: { email, password: DEMO_PASSWORD },
  });
  expect(login.status()).toBe(204);
  const me = await (await request.get(`${API}/api/v1/auth/me`)).json();
  return { csrf: me.csrf_token, memberships: me.memberships };
}

/** The saved UI language is part of the account, so tests that change it must restore it. */
export async function resetLocale(request: APIRequestContext, email: string): Promise<void> {
  const { csrf } = await apiLogin(request, email);
  const response = await request.patch(`${API}/api/v1/auth/me`, {
    data: { ui_locale: "tr" },
    headers: { "X-CSRF-Token": csrf },
  });
  expect(response.ok()).toBe(true);
}

export async function workspaceIds(
  request: APIRequestContext,
  email: string,
): Promise<Record<string, string>> {
  const { memberships } = await apiLogin(request, email);
  return Object.fromEntries(memberships.map((m) => [m.workspace_name, m.workspace_id]));
}

export async function loginViaUi(page: Page, email: string, password = DEMO_PASSWORD) {
  await page.getByLabel(/E-posta|Email/).fill(email);
  await page.getByLabel(/Parola|Password/).fill(password);
  await page.getByRole("button", { name: /Giriş yap|Sign in/ }).click();
}

/**
 * A link in the main navigation (bottom tabs or sidebar, whichever is shown). Scoped and exact
 * so that e.g. "Content" does not also match the "Skip to content" link.
 */
export function navLink(page: Page, label: string) {
  return page
    .getByRole("navigation", { name: /^(Ana gezinme|Main navigation)$/ })
    .getByRole("link", { name: label, exact: true });
}

/** True when the page overflows horizontally (the document is wider than the viewport). */
export async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
}

/**
 * Re-create the demo users, workspaces and facts. Tests that change facts call this first, so
 * every test (and every project, browser and viewport) starts from the same data. Sessions of
 * the re-created users are gone afterwards: sign in again.
 */
export function reseedDemo(): void {
  const backendDir = fileURLToPath(new URL("../../backend", import.meta.url));
  execFileSync("uv", ["run", "python", "-m", "app.cli", "seed", "--reset"], {
    cwd: backendDir,
    stdio: "ignore",
  });
}

/** Sign in through the UI and open a workspace by (part of) its name. */
export async function signInToWorkspace(page: Page, email: string, workspaceName: RegExp) {
  await page.goto("/login");
  await loginViaUi(page, email);
  await page.getByRole("link", { name: workspaceName }).click();
  await expect(page.getByRole("heading", { name: /^(Ana sayfa|Home)$/, level: 1 })).toBeVisible();
}

// ---------------------------------------------------------------------------------------------
// Phase 5 (content and scheduling): sample images, the dev simulator API and shared UI steps.
// ---------------------------------------------------------------------------------------------

/** The committed demo images (plan.md G19): a 1080x1920 story PNG and a 1080x1350 feed JPEG. */
export const SAMPLE_STORY = fileURLToPath(
  new URL("../../backend/app/demo/media/story-sample.png", import.meta.url),
);
export const SAMPLE_FEED = fileURLToPath(
  new URL("../../backend/app/demo/media/feed-sample.jpg", import.meta.url),
);

export const IST = "Europe/Istanbul";
export const WEB = `http://localhost:${process.env.E2E_WEB_PORT ?? "5173"}`;

/** Wall-clock date (YYYY-MM-DD) and time (HH:MM) in a time zone, `minutesAhead` from now. */
export function localFields(minutesAhead: number, timeZone = IST): { date: string; time: string } {
  const at = new Date(Date.now() + minutesAhead * 60_000);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(at)
      .map((part) => [part.type, part.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

/** Type a command into the command bar on the home page and send it. */
export async function say(page: Page, text: string) {
  await page.getByLabel("Komut").fill(text);
  await page.getByRole("button", { name: "Gönder" }).click();
}

/** The status badge of the open content item (`data-status` is the server state it renders). */
export function statusBadge(page: Page) {
  return page.locator("[data-status]").first();
}

/** Run what is due now through the dev API (deterministic progression; no waiting for the worker). */
export async function runDueJobs(request: APIRequestContext, csrf: string): Promise<number> {
  const response = await request.post(`${API}/api/v1/dev/jobs/run-due`, {
    headers: { "X-CSRF-Token": csrf },
  });
  expect(response.ok()).toBe(true);
  return (await response.json()).ran as number;
}

/** Script the next call(s) of the simulated Instagram to fail (dev API). */
export async function addFailureRule(
  request: APIRequestContext,
  csrf: string,
  workspaceId: string,
  operation: string,
  mode: string,
  remaining: number | null = 1,
) {
  const response = await request.post(`${API}/api/v1/dev/workspaces/${workspaceId}/failure-rules`, {
    data: { operation, mode, remaining },
    headers: { "X-CSRF-Token": csrf },
  });
  expect(response.status()).toBe(201);
}

/**
 * What the seeded history (yesterday, H16) already put in each studio: one published feed post
 * (title below, so a test can tell it from its own posts) and one failed one.
 */
export const SEEDED_PUBLISHED_POSTS = 1;
export const SEEDED_POST_TITLE = "Haftalık paylaşım";

/** The content cards a test created itself: the seeded history posts are left out. */
export function ownContentCards(page: Page) {
  return page.getByTestId("content-card").filter({ hasNotText: SEEDED_POST_TITLE });
}

/** What the simulated Instagram has published (read-only; the evidence of "exactly one post"). */
export async function simulatorPublished(
  request: APIRequestContext,
  workspaceId: string,
): Promise<{ media_id: string; media_type: string }[]> {
  const response = await request.get(`${API}/api/v1/dev/workspaces/${workspaceId}/simulator/published`);
  expect(response.ok()).toBe(true);
  return (await response.json()).items;
}

/** Upload an image through the editor's file input and wait until it is attached and shown. */
export async function attachImage(page: Page, file: string) {
  await page.locator('input[type="file"]').setInputFiles(file);
  await expect(page.getByRole("img", { name: "Seçilen görselin önizlemesi" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Kaydedildi")).toBeVisible();
}

/** Open the schedule sheet of the open draft and pick a time (wall-clock, workspace time zone). */
export async function openScheduleSheet(page: Page) {
  await page.getByRole("button", { name: "Zamanla", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Zamanla" });
  await expect(sheet).toBeVisible();
  return sheet;
}

// ---------------------------------------------------------------------------------------------
// Phase 6 (reports, activity, failure UX): the report API, the simulator and layout checks.
// ---------------------------------------------------------------------------------------------

/**
 * Fail when the page is wider than the viewport (AC-X4). Called on every main screen at 390x844
 * (the iPhone 13 and, within a few pixels, the Pixel 7 projects). `scrollWidth` of the document
 * is what a person can scroll sideways, so it must not exceed the window width.
 */
export async function expectNoHorizontalScroll(page: Page, where = "") {
  const sizes = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    inner: window.innerWidth,
  }));
  expect(sizes.scroll, `horizontal scroll on ${where || page.url()}`).toBeLessThanOrEqual(sizes.inner);
}

export interface ReportMetric {
  key: string;
  value: number | null;
  link: { api: string | null; route: string | null };
}

/** The daily report through the API (today, or a local date YYYY-MM-DD). */
export async function dailyReport(
  request: APIRequestContext,
  workspaceId: string,
  date?: string,
): Promise<{ metrics: ReportMetric[]; has_simulated_data: boolean; local_date: string }> {
  const query = date ? `?date=${date}` : "";
  const response = await request.get(`${API}/api/v1/workspaces/${workspaceId}/reports/daily${query}`);
  expect(response.ok()).toBe(true);
  return response.json();
}

export function metricValue(report: { metrics: ReportMetric[] }, key: string): number {
  const metric = report.metrics.find((m) => m.key === key);
  expect(metric, `metric ${key}`).toBeDefined();
  return metric!.value ?? 0;
}

/** A scripted customer message through the signed-webhook path (dev API); see the Dev panel. */
export async function simulateMessage(
  request: APIRequestContext,
  csrf: string,
  workspaceId: string,
  scriptId: string,
) {
  const response = await request.post(
    `${API}/api/v1/dev/workspaces/${workspaceId}/simulate/customer-message`,
    { data: { script_id: scriptId }, headers: { "X-CSRF-Token": csrf } },
  );
  expect(response.ok()).toBe(true);
}

/** Sign in as the owner through the API and return what the Phase 6 scenarios need. */
export async function ownerSetup(
  request: APIRequestContext,
  workspaceName = "Gölkent Fitness & Pilates",
  email = "owner@demo.local",
): Promise<{ csrf: string; workspaceId: string }> {
  const { csrf, memberships } = await apiLogin(request, email);
  const workspace = memberships.find((m) => m.workspace_name === workspaceName);
  expect(workspace).toBeDefined();
  return { csrf, workspaceId: workspace!.workspace_id };
}

/** Open an entry of the More menu by its (Turkish) name. */
export async function openMore(page: Page, linkName: string | RegExp) {
  await navLink(page, "Daha fazla").click();
  // Exact: the notification bell is also a link named "Bildirimler, N okunmamış bildirim".
  await page.getByRole("link", { name: linkName, exact: typeof linkName === "string" }).click();
}

/**
 * A feed post with its picture, approved by the owner. It publishes right now (the dev "run due
 * jobs" API then moves it along) or at a wall-clock time of the workspace. Returns the item id.
 */
export async function submitFeedPost(
  request: APIRequestContext,
  { csrf, workspaceId }: { csrf: string; workspaceId: string },
  schedule: "now" | { local_date: string; local_time: string } = "now",
  title = "Hafta sonu gönderisi",
): Promise<string> {
  const base = `${API}/api/v1/workspaces/${workspaceId}`;
  const headers = { "X-CSRF-Token": csrf };
  const upload = await request.post(`${base}/media`, {
    headers,
    multipart: {
      file: { name: "feed-sample.jpg", mimeType: "image/jpeg", buffer: readFileSync(SAMPLE_FEED) },
    },
  });
  expect(upload.status()).toBe(201);
  const created = await request.post(`${base}/content-items`, {
    headers,
    data: {
      content_type: "feed_image",
      title,
      caption: "Hafta sonu görüşürüz!",
      media_asset_id: (await upload.json()).id,
      client_request_id: randomUUID(),
    },
  });
  expect(created.status()).toBe(201);
  const item = await created.json();
  const submitted = await request.post(`${base}/content-items/${item.id}/submit`, {
    headers,
    data: { schedule, self_approve: true, expected_version: item.version },
  });
  expect(submitted.ok(), await submitted.text()).toBe(true);
  return item.id as string;
}

/** Pending reply approvals of a workspace (ids and the hash the owner would have seen). */
export async function pendingReplyApprovals(
  request: APIRequestContext,
  workspaceId: string,
): Promise<{ id: string; payload_hash: string }[]> {
  const response = await request.get(
    `${API}/api/v1/workspaces/${workspaceId}/approvals?status=pending&action=reply.send`,
  );
  expect(response.ok()).toBe(true);
  return (await response.json()).items;
}

/** Approve one approval the way the Approve button does (explicit id and hash). */
export async function approve(
  request: APIRequestContext,
  csrf: string,
  workspaceId: string,
  approval: { id: string; payload_hash: string },
) {
  const response = await request.post(
    `${API}/api/v1/workspaces/${workspaceId}/approvals/${approval.id}/decision`,
    {
      data: { decision: "approve", payload_hash: approval.payload_hash },
      headers: { "X-CSRF-Token": csrf },
    },
  );
  expect(response.ok()).toBe(true);
}

/** The simulated Instagram account of a workspace, as the API shows it. */
export async function accountStatus(
  request: APIRequestContext,
  workspaceId: string,
): Promise<string> {
  const response = await request.get(`${API}/api/v1/workspaces/${workspaceId}/social-accounts`);
  expect(response.ok()).toBe(true);
  const body = await response.json();
  const items = Array.isArray(body) ? body : body.items;
  return items[0].status as string;
}

/**
 * Pick a language button on the Settings screen and wait until the choice is saved on the
 * account. The screen changes at once; the save is a request that follows, and a reload before
 * it lands would read the old language back.
 */
export async function chooseLanguage(page: Page, name: "English" | "Türkçe") {
  const saved = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/me") && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name }).click();
  expect((await saved).ok()).toBe(true);
}
