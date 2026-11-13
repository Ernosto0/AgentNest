import { describe, expect, it } from "vitest";
import { describeUserAgent } from "./deviceLabel";

describe("describeUserAgent", () => {
  it.each([
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      { browser: "Chrome", os: "Windows", kind: "desktop" },
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
      { browser: "Edge", os: "Windows", kind: "desktop" },
    ],
    [
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
      { browser: "Safari", os: "macOS", kind: "desktop" },
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
      { browser: "Safari", os: "iOS", kind: "phone" },
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0 Mobile/15E148 Safari/604.1",
      { browser: "Chrome", os: "iOS", kind: "phone" },
    ],
    [
      "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
      { browser: "Safari", os: "iPadOS", kind: "tablet" },
    ],
    [
      "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
      { browser: "Samsung Internet", os: "Android", kind: "phone" },
    ],
    [
      "Mozilla/5.0 (Linux; Android 13; SM-X700) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      { browser: "Chrome", os: "Android", kind: "tablet" },
    ],
    [
      "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
      { browser: "Firefox", os: "Linux", kind: "desktop" },
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 YaBrowser/24.10.0.0 Safari/537.36",
      { browser: "Yandex Browser", os: "Windows", kind: "desktop" },
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/114.0.0.0",
      { browser: "Opera", os: "Windows", kind: "desktop" },
    ],
  ])("recognises %s", (ua, expected) => {
    expect(describeUserAgent(ua)).toEqual(expected);
  });

  it.each([null, undefined, "", "   ", "testclient", "python-requests/2.32", "curl/8.4.0", "Mozilla/5.0"])(
    "labels %s as unknown instead of guessing",
    (ua) => {
      expect(describeUserAgent(ua)).toEqual({ browser: null, os: null, kind: "unknown" });
    },
  );

  it("keeps a known platform when the browser is unfamiliar", () => {
    expect(describeUserAgent("SomeApp/1.0 (Windows NT 10.0)")).toEqual({ browser: null, os: "Windows", kind: "desktop" });
  });
});
