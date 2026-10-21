import { expect, test } from "@playwright/test";
import {
  API,
  accountStatus,
  addFailureRule,
  approve,
  expectNoHorizontalScroll,
  localFields,
  navLink,
  openMore,
  ownerSetup,
  pendingReplyApprovals,
  reseedDemo,
  runDueJobs,
  signInToWorkspace,
  simulateMessage,
  statusBadge,
  submitFeedPost,
} from "./helpers";

// Scenario G: the Instagram connection fails (docs/product/acceptance-criteria.md AC-G1, AC-G3;
// workflows.md G). The failure is scripted through the dev API (failure rules); the dev "run due
// jobs" and "health check" routes move time along, so nothing waits for real minutes.

const OWNER = "owner@demo.local";
const GYM = /Gölkent Fitness & Pilates/;

test.beforeEach(() => {
  reseedDemo();
});

test("G1: a revoked token turns Home red and the post waits; reconnecting sends the reply once", async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  const env = await ownerSetup(request);
  await addFailureRule(request, env.csrf, env.workspaceId, "send", "auth_revoked", null);
  // A post that falls due one to two minutes from now: by then the account will need the owner
  // (a post cannot be scheduled once it does, so it has to exist before).
  const due = localFields(2);
  const contentId = await submitFeedPost(request, env, { local_date: due.date, local_time: due.time });
  await simulateMessage(request, env.csrf, env.workspaceId, "price");

  await signInToWorkspace(page, OWNER, GYM);
  // Healthy so far (wait for the account to be shown first: a count of 0 alone is true before load).
  await expect(page.getByTestId("home-connection")).toHaveAttribute("data-status", "connected", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("banner-needs-reauth")).toHaveCount(0);
  await navLink(page, "Gelen kutusu").click();
  await page.getByRole("link", { name: /Ayşe/ }).click({ timeout: 20_000 });
  const card = page.getByTestId("draft-card");
  await expect(card).toHaveAttribute("data-draft-status", "pending_approval", { timeout: 25_000 });
  await card.getByRole("button", { name: "Onayla ve gönder" }).click();

  // The send fails with a revoked token: the reply is kept (not "sent"), the account needs the owner.
  await expect.poll(() => accountStatus(request, env.workspaceId), { timeout: 30_000 }).toBe(
    "needs_reauth",
  );
  await expect(card).not.toHaveAttribute("data-draft-status", "sent");

  // AC-G1: the red banner on Home (icon and words, not colour alone), with the way out.
  await navLink(page, "Ana sayfa").click();
  const banner = page.getByTestId("banner-needs-reauth");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Instagram bağlantınız yenilenmeli.");
  await expect(page.getByTestId("home-connection")).toHaveAttribute("data-status", "needs_reauth");
  await expectNoHorizontalScroll(page, "home with the reauth banner");

  // ...and the critical notification.
  await expect(page.getByTestId("notification-count")).toBeVisible();
  await openMore(page, "Bildirimler");
  const critical = page.locator('[data-severity="critical"]').filter({
    hasText: "Instagram hesabınızı yeniden bağlayın",
  });
  await expect(critical.first()).toBeVisible();
  await expect(critical.first()).toContainText("Acil");
  await expect(critical.first().getByTestId("simulated-badge")).toBeVisible(); // AC-X2
  await expectNoHorizontalScroll(page, "notifications");

  // The system health screen shows the account status too.
  await openMore(page, "Sistem durumu");
  await expect(page.getByRole("heading", { name: "Sistem durumu", level: 1 })).toBeVisible();
  await expect(page.getByTestId("health-account").getByTestId("account-status-badge")).toHaveAttribute(
    "data-status",
    "needs_reauth",
  );
  await expectNoHorizontalScroll(page, "system health");

  // The post fell due while the account could not be used: held, in plain words, not published.
  await page.goto(`/w/${env.workspaceId}/content/${contentId}`);
  await expect(statusBadge(page)).toHaveAttribute("data-status", "on_hold", { timeout: 150_000 });
  await expect(statusBadge(page)).toContainText("Beklemede");
  await expect(page.getByText("Yayınlandı")).toHaveCount(0);

  // Reconnect on the connections screen (owner): the banner is gone, the reply goes out once.
  await page.goto(`/w/${env.workspaceId}`);
  await page.getByTestId("banner-needs-reauth").getByRole("link", { name: "Bağlantıyı yenile" }).click();
  await expect(page.getByRole("heading", { name: "Instagram bağlantısı", level: 1 })).toBeVisible();
  await expect(page.getByTestId("account-status-badge")).toHaveAttribute("data-status", "needs_reauth");
  await page.getByRole("button", { name: "Yeniden bağlan (simülasyon)" }).click();
  await expect(page.getByTestId("account-status-badge")).toHaveAttribute("data-status", "connected");
  await expect(page.getByTestId("simulated-badge").first()).toBeVisible(); // the account is simulated
  await expectNoHorizontalScroll(page, "connections");

  await navLink(page, "Ana sayfa").click();
  await expect(page.getByTestId("home-connection")).toHaveAttribute("data-status", "connected");
  await expect(page.getByTestId("banner-needs-reauth")).toHaveCount(0);

  await runDueJobs(request, env.csrf); // the reconnect queued the waiting reply; this just hurries it
  await navLink(page, "Gelen kutusu").click();
  await page.getByRole("link", { name: /Ayşe/ }).click();
  await expect(page.getByTestId("draft-card")).toHaveAttribute("data-draft-status", "sent", {
    timeout: 40_000,
  });
  await expect(page.getByTestId("draft-card")).toContainText("Gönderildi");
  // Exactly one message went out, and the revoked-token rule ended with the old token.
  const rules = await request.get(`${API}/api/v1/dev/workspaces/${env.workspaceId}/failure-rules`);
  const modes = (await rules.json()).items.map((rule: { mode: string }) => rule.mode);
  expect(modes).not.toContain("auth_revoked");

  // Reconnecting does not resume a held post: it waits for the owner (Beklemede).
  await page.goto(`/w/${env.workspaceId}/content/${contentId}`);
  await expect(statusBadge(page)).toHaveAttribute("data-status", "on_hold");
});

test("G3: five failed sends make the account unstable (amber banner); a health check clears it", async ({
  page,
  request,
}) => {
  test.setTimeout(150_000);
  const env = await ownerSetup(request);
  const already = new Set((await pendingReplyApprovals(request, env.workspaceId)).map((a) => a.id));
  await addFailureRule(request, env.csrf, env.workspaceId, "send", "transient", 5);
  // The worker probes every degraded account on its own (a minute-by-minute scheduler tick, the
  // account_health_check job; workflows.md G.2), and a probe that works closes the circuit. That
  // can happen any time while this test looks at the amber state. While Instagram "still
  // fails" the probe fails too (cooldown extended, account stays degraded): the rule is removed
  // below together with the others, before the health check that is meant to recover.
  await addFailureRule(request, env.csrf, env.workspaceId, "profile", "transient", null);
  // Five different customers, five questions, five approved replies: all driven through the API.
  for (const script of ["price", "hours", "location", "trial", "english_tourist"]) {
    await simulateMessage(request, env.csrf, env.workspaceId, script);
  }
  let fresh: { id: string; payload_hash: string }[] = [];
  await expect
    .poll(
      async () => {
        fresh = (await pendingReplyApprovals(request, env.workspaceId)).filter((a) => !already.has(a.id));
        return fresh.length;
      },
      { timeout: 60_000 },
    )
    .toBe(5);
  for (const approval of fresh) await approve(request, env.csrf, env.workspaceId, approval);

  // Each send fails once within seconds: five within ten minutes opens the circuit.
  await expect
    .poll(
      async () => {
        await runDueJobs(request, env.csrf);
        return accountStatus(request, env.workspaceId);
      },
      { timeout: 60_000 },
    )
    .toBe("degraded");

  await signInToWorkspace(page, OWNER, GYM);
  const banner = page.getByTestId("banner-degraded");
  await expect(banner).toBeVisible({ timeout: 15_000 });
  await expect(banner).toContainText("Instagram'a şu an ulaşılamıyor");
  await expect(page.getByTestId("home-connection")).toHaveAttribute("data-status", "degraded");
  await expect(page.getByTestId("banner-needs-reauth")).toHaveCount(0); // not the red kind
  await expectNoHorizontalScroll(page, "home with the degraded banner");

  // The connections screen says until when nothing is sent (workspace time).
  await openMore(page, "Instagram bağlantısı");
  await expect(page.getByRole("heading", { name: "Instagram bağlantısı", level: 1 })).toBeVisible();
  await expect(page.getByTestId("account-status-badge")).toHaveAttribute("data-status", "degraded", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("degraded-until")).toContainText(/\d{2}:\d{2}/);
  await expectNoHorizontalScroll(page, "connections while degraded");

  // Recovery: the rules are used up, the Instagram answers again, the health check says so.
  const rules = await request.get(`${API}/api/v1/dev/workspaces/${env.workspaceId}/failure-rules`);
  for (const rule of (await rules.json()).items) {
    const removed = await request.delete(
      `${API}/api/v1/dev/workspaces/${env.workspaceId}/failure-rules/${rule.id}`,
      { headers: { "X-CSRF-Token": env.csrf } },
    );
    expect(removed.status()).toBe(204);
  }
  const check = await request.post(`${API}/api/v1/dev/workspaces/${env.workspaceId}/health-check`, {
    headers: { "X-CSRF-Token": env.csrf },
  });
  expect(await check.json()).toEqual({ checked: 1, recovered: 1 });

  // Load Home afresh (as the owner would after the notification): the in-page navigation right
  // after the health check sometimes did not render in WebKit for several seconds.
  await page.goto(`/w/${env.workspaceId}`);
  await expect(page.getByRole("heading", { name: "Ana sayfa", level: 1 })).toBeVisible();
  await expect(page.getByTestId("home-connection")).toHaveAttribute("data-status", "connected", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("banner-degraded")).toHaveCount(0);
});
