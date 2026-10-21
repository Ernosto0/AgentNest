import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import {
  apiLogin,
  expectNoHorizontalScroll,
  localFields,
  ownerSetup,
  pendingReplyApprovals,
  reseedDemo,
  simulateMessage,
} from "./helpers";

// Accessibility (testing-strategy.md): axe on the main screens, no serious or critical
// violations. The projects cover a 390x844 phone (iPhone 13), a 412 px phone (Pixel 7) and the
// desktop; every screen also has to fit the phone width (AC-X4). Fix the code, not the rules:
// there are no disabled rules and no excluded elements in this file.

const OWNER = "owner@demo.local";

test.beforeAll(() => {
  reseedDemo(); // read-only specs below, but the data must be the seeded one
});

async function audit(page: Page, name: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const lines = blocking.map(
    (v) =>
      `${v.impact} ${v.id}: ${v.help} -> ${v.nodes
        .slice(0, 3)
        .map((n) => n.target.join(" "))
        .join(" | ")} (${v.nodes.length} node(s))`,
  );
  expect(lines, `axe on ${name}`).toEqual([]);
}

/** Wait until a screen has its heading and has finished loading, then check layout and axe. */
async function check(page: Page, name: string) {
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await expect(page.getByText(/Yükleniyor/)).toHaveCount(0, { timeout: 15_000 });
  await expectNoHorizontalScroll(page, name);
  await audit(page, name);
}

test.describe("signed out", () => {
  test("login page", async ({ page }) => {
    await page.goto("/login");
    await check(page, "login");
  });

  test("invite accept page", async ({ page }) => {
    await page.goto("/invite/any-token-shows-the-form");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoHorizontalScroll(page, "invite");
    await audit(page, "invite");
  });
});

test.describe("signed in as the owner of the gym", () => {
  let base = "";

  test.beforeEach(async ({ page, request }) => {
    const { workspaceId } = await ownerSetup(request);
    base = `/w/${workspaceId}`;
    await apiLogin(page.request, OWNER); // the page shares this context's session cookie
  });

  const screens: [string, string][] = [
    ["home", ""],
    ["inbox", "/inbox"],
    ["content", "/content"],
    ["approvals", "/approvals"],
    ["more", "/more"],
    ["settings", "/more/settings"],
    ["knowledge", "/more/knowledge"],
    ["knowledge: pricing", "/more/knowledge/pricing"],
    ["automation", "/more/automation"],
    ["reports", "/more/reports"],
    ["activity", "/more/activity"],
    ["notifications", "/more/notifications"],
    ["members", "/more/settings/members"],
    ["connections", "/more/settings/connections"],
    ["system health", "/more/settings/system-health"],
    ["dev panel", "/more/dev"],
  ];
  for (const [name, path] of screens) {
    test(name, async ({ page }) => {
      await page.goto(`${base}${path}`);
      await check(page, name);
    });
  }

  test("a conversation", async ({ page }) => {
    await page.goto(`${base}/inbox`);
    await page.getByRole("link", { name: /Ayşe|Mehmet|Zeynep|Can|Burak|Selin|Elif|Kerem|Sarah|Ivan/ }).first().click();
    await expect(page.getByTestId("messages")).toBeVisible();
    await check(page, "conversation");
  });

  test("a content item", async ({ page }) => {
    await page.goto(`${base}/content?tab=problems`); // the seeded history has a failed post
    await page.getByTestId("content-card").first().click();
    await expect(page.locator("[data-status]").first()).toBeVisible();
    await check(page, "content detail");
  });

  test("a report drill-down", async ({ page }) => {
    const yesterday = localFields(-24 * 60).date;
    await page.goto(`${base}/more/reports/${yesterday}/inbound_messages`);
    await expect(page.getByTestId("metric-item").first()).toBeVisible();
    await check(page, "report drill-down");
  });

  test("an approval sheet", async ({ page, request }) => {
    // The seeded waiting reply is from yesterday and may have expired: ask a fresh question.
    const { csrf, workspaceId } = await ownerSetup(request);
    await simulateMessage(request, csrf, workspaceId, "price");
    await expect.poll(async () => (await pendingReplyApprovals(request, workspaceId)).length, {
      timeout: 30_000,
    }).toBeGreaterThan(0);
    await page.goto(`${base}/approvals`);
    await page.locator("[data-approval-id]").first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await check(page, "approval sheet");
  });
});
