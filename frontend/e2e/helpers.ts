import { execFileSync } from "node:child_process";
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
