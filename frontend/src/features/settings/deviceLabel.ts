/**
 * A readable description of a stored browser User-Agent ("Chrome", "Windows", desktop).
 *
 * Deliberately conservative: it only recognises well-known product tokens and returns `null`
 * for anything else, so an unfamiliar client is labelled "unknown" instead of being guessed.
 * Brand and platform names are proper nouns and are not translated.
 */

export type DeviceKind = "desktop" | "phone" | "tablet" | "unknown";

export interface DeviceInfo {
  browser: string | null;
  os: string | null;
  kind: DeviceKind;
}

// Order matters: Chromium-based browsers also send "Chrome/" and "Safari/", and Chrome on iOS
// sends "Safari/" too, so the more specific tokens are checked first.
const BROWSERS: readonly (readonly [RegExp, string])[] = [
  [/\bEdg(?:e|A|iOS)?\//, "Edge"],
  [/\b(?:OPR|OPiOS)\/|\bOpera\b/, "Opera"],
  [/\bSamsungBrowser\//, "Samsung Internet"],
  [/\bYaBrowser\//, "Yandex Browser"],
  [/\b(?:Firefox|FxiOS)\//, "Firefox"],
  [/\bCriOS\//, "Chrome"],
  [/\bChromium\//, "Chromium"],
  [/\bChrome\//, "Chrome"],
  [/\bVersion\/[\d.]+.*\bSafari\//, "Safari"],
];

const OPERATING_SYSTEMS: readonly (readonly [RegExp, string])[] = [
  [/\bWindows (?:NT|Phone)\b/, "Windows"],
  [/\biPad\b/, "iPadOS"],
  [/\b(?:iPhone|iPod)\b/, "iOS"],
  [/\bAndroid\b/, "Android"],
  [/\bCrOS\b/, "ChromeOS"],
  [/\bMac OS X\b|\bMacintosh\b/, "macOS"],
  [/\bLinux\b/, "Linux"],
];

function firstMatch(ua: string, table: readonly (readonly [RegExp, string])[]): string | null {
  for (const [pattern, name] of table) if (pattern.test(ua)) return name;
  return null;
}

export function describeUserAgent(ua: string | null | undefined): DeviceInfo {
  const value = (ua ?? "").trim();
  if (!value) return { browser: null, os: null, kind: "unknown" };
  const browser = firstMatch(value, BROWSERS);
  const os = firstMatch(value, OPERATING_SYSTEMS);
  let kind: DeviceKind = "unknown";
  if (/\biPad\b|\bTablet\b/.test(value) || (os === "Android" && !/\bMobile\b/.test(value))) kind = "tablet";
  else if (/\b(?:iPhone|iPod)\b|\bMobile\b/.test(value)) kind = "phone";
  else if (os === "Windows" || os === "macOS" || os === "Linux" || os === "ChromeOS") kind = "desktop";
  return { browser, os, kind };
}
