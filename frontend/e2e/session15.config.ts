import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  outputDir: join(tmpdir(), "agentnest-s15-browser"),
  testDir: ".",
  testMatch: "agent-work.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 120000,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? "5115"}`,
    locale: "en-US",
    timezoneId: "Europe/Istanbul",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 13"], viewport: { width: 390, height: 844 } },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } },
    },
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
