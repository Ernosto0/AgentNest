import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const CI = Boolean(process.env.CI);
const backendDir = fileURLToPath(new URL("../../backend", import.meta.url));
const frontendDir = fileURLToPath(new URL("..", import.meta.url));
// Ports can be moved (e.g. a second checkout running its own stack); the defaults are the documented ones.
const API_PORT = process.env.E2E_API_PORT ?? "8000";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "5173";

/**
 * End-to-end tests run against the real stack: Postgres (docker compose) with migrations
 * applied, the API, and the SPA. The demo data is re-seeded in global-setup.ts.
 * Order of operations is the one in docs/operations/local-development.md.
 */
export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  globalSetup: "./global-setup.ts",
  // One worker: the specs share the seeded demo accounts (ui_locale is saved per account).
  workers: 1,
  fullyParallel: false,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    // The primary market: the app picks the browser language until an account language is known.
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
  },
  projects: [
    { name: "mobile-webkit", use: { ...devices["iPhone 13"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: `uv run uvicorn app.main:create_app --factory --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/readyz`,
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      // The worker runs the background jobs (command interpretation, extraction). It has no
      // port, so we wait for its startup log line; the poll interval is short for the tests.
      command: "uv run python -m app.worker",
      cwd: backendDir,
      wait: { stderr: /startup/ },
      env: { WORKER_POLL_INTERVAL_SECONDS: "0.2" },
      timeout: 60_000,
    },
    {
      // CI serves the production build; locally the dev server is faster to start.
      command: CI
        ? `npm run build && npm run preview -- --strictPort --port ${WEB_PORT}`
        : `npm run dev -- --strictPort --port ${WEB_PORT}`,
      cwd: frontendDir,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
