import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";
import baseline from "./playwright.config";

// This suite may reseed data. Require an explicitly selected disposable local database.
const database = process.env.DATABASE_URL ?? "";
if (!/127\.0\.0\.1:55433\/agentnest_core_ui_test$/.test(database)) {
  throw new Error("Core redesign E2E requires the isolated agentnest_core_ui_test database.");
}
Object.assign(process.env, {
  APP_ENV: "development",
  MIGRATION_DATABASE_URL: database,
  MEDIA_LOCAL_ROOT: fileURLToPath(new URL("../../.tmp/core-test-media", import.meta.url)),
  INSTAGRAM_ENABLED_PROVIDERS: "mock",
  LLM_PROVIDER: "fake",
  MEDIA_STORAGE_BACKEND: "local",
  COOKIE_SECURE: "false",
});
export default defineConfig({
  ...baseline,
  testMatch: "agent-settings.spec.ts",
  timeout: 120_000,
  outputDir: "../../docs/ui-core-redesign/stack-browser",
  webServer: baseline.webServer && Array.isArray(baseline.webServer) ? baseline.webServer.map(server => ({ ...server, reuseExistingServer: false })) : baseline.webServer,
});
