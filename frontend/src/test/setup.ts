import "@testing-library/jest-dom/vitest";
import { afterEach, beforeAll, beforeEach } from "vitest";
import { preloadRoutes } from "@/app/router";
import i18n, { setLanguage } from "@/i18n";

beforeAll(async () => {
  await preloadRoutes();
});

beforeEach(async () => {
  window.localStorage.clear();
  await setLanguage("tr");
});

afterEach(async () => {
  await i18n.changeLanguage("tr");
});
