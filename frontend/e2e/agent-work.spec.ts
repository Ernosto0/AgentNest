import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { hasHorizontalScroll } from "./helpers";

function fixture(mode: string, id?: string) {
  const args = [
    "exec",
    "-e",
    `DATABASE_URL=${process.env.E2E_FIXTURE_DATABASE_URL}`,
    process.env.E2E_FIXTURE_CONTAINER ?? "agentnest-s14-api",
    "uv",
    "run",
    "python",
    "-m",
    "tests.browser.agent_work_fixture",
    mode,
    ...(id ? [id] : []),
  ];
  const result = execFileSync("docker", args, { encoding: "utf8" });
  return JSON.parse(result.trim().split(/\r?\n/).at(-1)!);
}
test("comment-to-DM owner information answer resumes verified customer continuation", async ({
  page,
}) => {
  test.skip(
    !process.env.E2E_FIXTURE_DATABASE_URL,
    "Explicit disposable offline fixture database required",
  );
  page.on("pageerror", (error) => console.error("Browser runtime:", error.message));
  const world = fixture("prepare");
  await page.goto("/login");
  await page.getByLabel(/Email|E-posta/).fill(world.email);
  await page.getByLabel(/Password|Parola/).fill(world.password);
  await page.getByRole("button", { name: /Sign in|Giriş yap/ }).click();
  await page.waitForURL((url) => !url.pathname.includes("login"));
  await page.goto(
    `/w/${world.workspace}/more/agent/questions/${world.question}?account=${world.account}`,
  );
  await expect(page.getByText("Can this customer receive a one-off exception?")).toBeVisible();
  await expect(page.getByText(/does not approve a post or message/)).toBeVisible();
  await page
    .getByLabel("Business answer")
    .fill("A one-off exception is available for this request.");
  await page.getByRole("button", { name: "Save information answer" }).click();
  await expect(page.getByText(/Information recorded/)).toBeVisible();
  expect((await new AxeBuilder({ page }).include("main").analyze()).violations).toEqual([]);
  expect(await hasHorizontalScroll(page)).toBe(false);
  const outcome = fixture("resume", world.question);
  expect(outcome.outbound_count).toBe(1);
  expect(outcome.texts[0]).toContain("one-off exception");
  await page.goto(`/w/${world.workspace}/inbox/${world.conversation}`);
  await expect(page.getByTestId("messages")).toContainText("one-off exception");
  await expect(page.getByText("Performed and verified")).toBeVisible();
  await expect(page.getByText("SIMULATED", { exact: false }).first()).toBeVisible();
  expect(await hasHorizontalScroll(page)).toBe(false);
  await page.screenshot({ path: test.info().outputPath("s15.png"), fullPage: true });
  const localeStatus = await page.evaluate(
    async (api) => {
      const me = await (await fetch(`${api}/api/v1/auth/me`, { credentials: "include" })).json();
      const response = await fetch(`${api}/api/v1/auth/me`, {
        method: "PATCH",
        credentials: "include",
        headers: { "X-CSRF-Token": me.csrf_token, "Content-Type": "application/json" },
        body: JSON.stringify({ ui_locale: "tr" }),
      });
      return response.status;
    },
    `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8015"}`,
  );
  expect(localeStatus).toBe(200);
  await page.reload();
  await expect(page.getByText("Asistan çalışması")).toBeVisible();
  expect(await hasHorizontalScroll(page)).toBe(false);
});
