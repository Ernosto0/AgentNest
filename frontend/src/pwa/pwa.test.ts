import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";
import { urlBase64ToBytes } from "./push";

const PUBLIC = resolve(__dirname, "../../public");
const ORIGIN = "https://app.example.com";

type Listener = (event: Record<string, unknown>) => void;

/** Run public/sw.js against a fake service-worker scope and return what it registered. */
function loadWorker() {
  const listeners = new Map<string, Listener>();
  const shown: { title: string; options: Record<string, unknown> }[] = [];
  const opened: string[] = [];
  const windows: { url: string; focus: () => Promise<void>; navigate: (u: string) => Promise<void> }[] = [];
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, fn: Listener) => listeners.set(type, fn),
    skipWaiting: () => Promise.resolve(),
    registration: {
      showNotification: (title: string, options: Record<string, unknown>) => {
        shown.push({ title, options });
        return Promise.resolve();
      },
    },
    clients: {
      claim: () => Promise.resolve(),
      matchAll: () => Promise.resolve(windows),
      openWindow: (url: string) => {
        opened.push(url);
        return Promise.resolve(null);
      },
    },
  };
  runInNewContext(readFileSync(resolve(PUBLIC, "sw.js"), "utf8"), { self, URL, Promise });
  return { listeners, shown, opened, windows };
}

async function push(worker: ReturnType<typeof loadWorker>, payload: unknown) {
  const waits: Promise<unknown>[] = [];
  worker.listeners.get("push")?.({
    data: { json: () => payload },
    waitUntil: (p: Promise<unknown>) => waits.push(p),
  });
  await Promise.all(waits);
}

async function click(worker: ReturnType<typeof loadWorker>, data: unknown) {
  const closed = vi.fn();
  const waits: Promise<unknown>[] = [];
  worker.listeners.get("notificationclick")?.({
    notification: { close: closed, data },
    waitUntil: (p: Promise<unknown>) => waits.push(p),
  });
  await Promise.all(waits);
  expect(closed).toHaveBeenCalled();
}

describe("service worker (push only)", () => {
  it("handles push and notificationclick, and has no fetch handler or cache", () => {
    const worker = loadWorker();
    expect([...worker.listeners.keys()].sort()).toEqual(["activate", "install", "notificationclick", "push"]);
    const source = readFileSync(resolve(PUBLIC, "sw.js"), "utf8");
    expect(source).not.toMatch(/["']fetch["']/);
    expect(source).not.toMatch(/\bcaches\b/);
  });

  it("shows the notification with plain text and a same-origin link", async () => {
    const worker = loadWorker();
    await push(worker, { title: "Onay bekliyor", body: "Bir yanÄ±t onayÄ±nÄ±zÄ± bekliyor", url: "/w/1/approvals?x=1#a", tag: "approval" });
    expect(worker.shown).toHaveLength(1);
    expect(worker.shown[0]?.title).toBe("Onay bekliyor");
    expect(worker.shown[0]?.options).toMatchObject({
      body: "Bir yanÄ±t onayÄ±nÄ±zÄ± bekliyor",
      tag: "approval",
      data: { url: "/w/1/approvals?x=1#a" },
    });
  });

  it("falls back to a generic notification on a missing or broken payload", async () => {
    const worker = loadWorker();
    await push(worker, null);
    await push(worker, { title: 42, body: {}, url: 7 });
    expect(worker.shown.map((n) => n.title)).toEqual(["AgentNest", "AgentNest"]);
    expect(worker.shown[1]?.options).toMatchObject({ body: "", data: { url: "/" } });
  });

  it.each([
    "https://evil.example.org/phish",
    "//evil.example.org/phish",
    "http://app.example.com/downgrade",
    "javascript:alert(1)",
    "data:text/html,hi",
    "https://app.example.com.evil.org/",
    "",
    "https://",
  ])("never links to %j: the stored link becomes /", async (url) => {
    const worker = loadWorker();
    await push(worker, { title: "x", url });
    expect(worker.shown[0]?.options).toMatchObject({ data: { url: "/" } });
  });

  it("accepts an absolute URL on its own origin and keeps only the path", async () => {
    const worker = loadWorker();
    await push(worker, { title: "x", url: `${ORIGIN}/w/2/inbox?c=3` });
    expect(worker.shown[0]?.options).toMatchObject({ data: { url: "/w/2/inbox?c=3" } });
  });

  it("opens a window on the app origin on click, and / for a forged link", async () => {
    const worker = loadWorker();
    await click(worker, { url: "/w/1/approvals" });
    await click(worker, { url: "https://evil.example.org/" });
    await click(worker, undefined);
    expect(worker.opened).toEqual([`${ORIGIN}/w/1/approvals`, `${ORIGIN}/`, `${ORIGIN}/`]);
  });

  it("reuses an open app window instead of opening another", async () => {
    const worker = loadWorker();
    const focus = vi.fn(() => Promise.resolve());
    const navigate = vi.fn(() => Promise.resolve());
    worker.windows.push({ url: `${ORIGIN}/w/1/home`, focus, navigate });
    await click(worker, { url: "/w/1/approvals" });
    expect(focus).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith(`${ORIGIN}/w/1/approvals`);
    expect(worker.opened).toEqual([]);
  });
});

describe("web manifest and page", () => {
  const manifest = JSON.parse(readFileSync(resolve(PUBLIC, "manifest.webmanifest"), "utf8"));
  const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");

  it("is installable: name, standalone, start_url, 192 and 512 icons, a maskable icon", () => {
    expect(manifest).toMatchObject({ name: "AgentNest", display: "standalone", start_url: "/", scope: "/" });
    const sizes = manifest.icons.map((i: { sizes: string; purpose: string }) => `${i.sizes}:${i.purpose}`);
    expect(sizes).toEqual(expect.arrayContaining(["192x192:any", "512x512:any", "512x512:maskable"]));
    for (const icon of manifest.icons) {
      expect(() => readFileSync(resolve(PUBLIC, icon.src.slice(1)))).not.toThrow();
    }
  });

  it("is linked from the page with the icons, theme colour and description", () => {
    expect(html).toContain('rel="manifest" href="/manifest.webmanifest"');
    expect(html).toContain('rel="apple-touch-icon"');
    expect(html).toContain('name="description"');
    // One tag per colour scheme (media-specific); the app is light-only, so both match the manifest.
    const themeColors = [...html.matchAll(/<meta name="theme-color" media="\(prefers-color-scheme: (light|dark)\)" content="([^"]+)"/g)];
    expect(themeColors.map((m) => m[1])).toEqual(["light", "dark"]);
    for (const m of themeColors) expect(m[2]).toBe(manifest.theme_color);
  });
});

describe("urlBase64ToBytes", () => {
  it("decodes a base64url VAPID key (no padding, - and _)", () => {
    expect(Array.from(urlBase64ToBytes("AQID"))).toEqual([1, 2, 3]);
    expect(Array.from(urlBase64ToBytes("-_8"))).toEqual([251, 255]);
  });
});
