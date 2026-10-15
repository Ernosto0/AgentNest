import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts", "playwright-report", "test-results"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2023, globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Customer-supplied text must never be rendered as HTML (threat T15).",
        },
        {
          // AC 5: every visible string comes from the i18n catalogs, never from the source.
          selector: "JSXText[value=/\\p{L}{2,}/u]",
          message: "Visible text must come from the i18n catalogs: use {t('...')}.",
        },
        {
          selector:
            "JSXAttribute[name.name=/^(aria-label|title|alt|placeholder)$/] > Literal[value=/\\p{L}{2,}/u]",
          message: "Accessible names and placeholders must come from the i18n catalogs.",
        },
      ],
    },
  },
  {
    // Tests assert on literal text by design.
    files: ["**/*.test.{ts,tsx}", "src/test/**"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    // Node-side files: Playwright config/specs and build scripts.
    files: ["e2e/**/*.ts", "vite.config.ts", "scripts/**/*.mjs"],
    languageOptions: { globals: { ...globals.node } },
  },
);
