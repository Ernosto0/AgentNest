import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API serves /api, /webhooks and /oauth. The proxy keeps the SPA and the API on one
// origin in development, so the session cookie is first-party and CORS is not involved.
const API_TARGET = `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`;
const proxy = Object.fromEntries(
  ["/api", "/webhooks", "/oauth"].map((path) => [path, { target: API_TARGET, changeOrigin: false }]),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: { port: 5173, proxy },
  preview: { port: 5173, proxy },
  test: {
    environment: "jsdom",
    // Each worker owns a jsdom app. Bound memory/CPU use on the Windows demo machine.
    maxWorkers: 4,
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // Node cannot build a Request from a relative URL (browsers can), so tests use an absolute one.
    env: { VITE_API_BASE_URL: "http://localhost" },
  },
});
