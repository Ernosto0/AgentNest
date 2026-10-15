import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const CI = Boolean(process.env.CI);
const backendDir = fileURLToPath(new URL("../../backend", import.meta.url));
const frontendDir = fileURLToPath(new URL("..", import.meta.url));

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
    baseURL: "http://localhost:5173",
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
      command: "uv run uvicorn app.main:create_app --factory --port 8000",
      cwd: backendDir,
      url: "http://localhost:8000/readyz",
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      // CI serves the production build; locally the dev server is faster to start.
      command: CI
        ? "npm run build && npm run preview -- --strictPort"
        : "npm run dev -- --strictPort",
      cwd: frontendDir,
      url: "http://localhost:5173",
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
