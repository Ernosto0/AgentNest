import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import i18n, { setLanguage } from "@/i18n";

beforeEach(async () => {
  window.localStorage.clear();
  await setLanguage("tr");
});

afterEach(async () => {
  await i18n.changeLanguage("tr");
});
