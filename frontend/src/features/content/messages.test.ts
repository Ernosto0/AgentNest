import { describe, expect, it } from "vitest";
import enAi from "@/i18n/locales/en/ai.json";
import enCommon from "@/i18n/locales/en/common.json";
import enContent from "@/i18n/locales/en/content.json";
import trAi from "@/i18n/locales/tr/ai.json";
import trCommon from "@/i18n/locales/tr/common.json";
import trContent from "@/i18n/locales/tr/content.json";
import i18n from "@/i18n";
import { CAPABILITY_KEYS, SUBMIT_ITEM_CODES, capabilityLabel, checkMessage, timezoneLabel } from "./messages";
import { failureCode, failureText } from "./failure";
import { contentItem } from "@/test/contentFixtures";

function lookup(catalog: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);
}

// The error codes a publish can end in (observability §4) and the reasons a hold carries.
const PUBLISH_ERROR_CODES = [
  "MEDIA_REJECTED",
  "PUBLISH_DEADLINE_PASSED",
  "PUBLISH_QUOTA_EXHAUSTED",
  "PROVIDER_UNAVAILABLE",
  "PROVIDER_RATE_LIMITED",
  "PROVIDER_REJECTED",
  "CAPABILITY_MISSING",
  "ACCOUNT_NEEDS_REAUTH",
  "OUTCOME_UNKNOWN",
  "OUTCOME_UNCONFIRMED",
];

describe.each([
  ["tr", trContent, trCommon, trAi],
  ["en", enContent, enCommon, enAi],
] as const)("%s catalogs for the content flows", (_language, content, common, ai) => {
  it("has a text for every submit item code (G17)", () => {
    for (const code of SUBMIT_ITEM_CODES) {
      expect(typeof lookup(content, `content.editor.checks.${code}`), code).toBe("string");
    }
  });

  it("has what and next for every publish error code and the hold reasons", () => {
    for (const code of PUBLISH_ERROR_CODES) {
      expect(typeof lookup(common, `errors.${code}.what`), code).toBe("string");
      expect(typeof lookup(common, `errors.${code}.next`), code).toBe("string");
    }
    for (const reason of ["FACT_CHANGED", "ACCOUNT_UNAVAILABLE", "unknown"]) {
      expect(typeof lookup(content, `content.hold.${reason}.what`), reason).toBe("string");
      expect(typeof lookup(content, `content.hold.${reason}.next`), reason).toBe("string");
    }
    expect(typeof lookup(content, "content.failure.unknown.what")).toBe("string");
  });

  it("labels the capabilities an account can hold (G4)", () => {
    for (const key of CAPABILITY_KEYS) expect(typeof lookup(content, `content.capability.${key}`), key).toBe("string");
  });

  it("has a text for the notification kinds", () => {
    for (const key of [
      "content_on_hold",
      "content_on_hold_FACT_CHANGED",
      "content_on_hold_ACCOUNT_UNAVAILABLE",
      "content_published",
      "content_failed",
    ]) {
      expect(typeof lookup(ai, `notifications.type.${key}`), key).toBe("string");
    }
  });
});

describe("message helpers", () => {
  it("names the workspace clock: İstanbul saati", () => {
    expect(timezoneLabel("Europe/Istanbul", i18n.t.bind(i18n))).toBe("İstanbul saati");
    expect(timezoneLabel("Europe/Lisbon", i18n.t.bind(i18n))).toBe("Lisbon saati");
  });

  it("states a time in a clock gap with the zone label", () => {
    const text = checkMessage(
      {
        code: "SCHEDULE_TIME_NONEXISTENT",
        params: { local_date: "2026-03-29", local_time: "03:30", timezone: "Europe/Istanbul" },
      },
      i18n.t.bind(i18n),
    );
    expect(text).toContain("İstanbul saati");
    expect(text).toContain("03:30");
  });

  it("falls back to the server's own message for an unknown code", () => {
    expect(checkMessage({ code: "SOMETHING_NEW", params: {}, message: "Sunucu mesajı" }, i18n.t.bind(i18n))).toBe(
      "Sunucu mesajı",
    );
  });

  it("labels a capability, and shows an unknown one as its own name", () => {
    expect(capabilityLabel("publish_story_image", i18n.t.bind(i18n))).toBe("Story yayınlama");
    expect(capabilityLabel("publish_feed_image", i18n.t.bind(i18n))).toBe("Gönderi yayınlama");
    expect(capabilityLabel("something_else", i18n.t.bind(i18n))).toBe("something_else");
  });
});

describe("why a post is in trouble", () => {
  it("reads the code from the item, or an unknown outcome while checking", () => {
    expect(failureCode(contentItem({ status: "failed", last_error_code: "MEDIA_REJECTED" }))).toBe("MEDIA_REJECTED");
    expect(
      failureCode(
        contentItem({
          status: "retry_scheduled",
          last_error_code: null,
          operation: { status: "retry_wait", attempts: 1, next_attempt_at: null, last_error_code: "PROVIDER_UNAVAILABLE" },
        }),
      ),
    ).toBe("PROVIDER_UNAVAILABLE");
    expect(
      failureCode(
        contentItem({
          status: "publishing",
          operation: { status: "outcome_unknown", attempts: 1, next_attempt_at: null, last_error_code: null },
        }),
      ),
    ).toBe("OUTCOME_UNKNOWN");
    expect(failureCode(contentItem({ status: "publishing" }))).toBeNull();
    expect(failureCode(contentItem({ status: "scheduled" }))).toBeNull();
    expect(failureCode(contentItem({ status: "published" }))).toBeNull();
  });

  it("explains a code from the catalog and an unknown one generically", () => {
    const t = i18n.t.bind(i18n);
    expect(failureText("MEDIA_REJECTED", t).what).toBe("Instagram görseli işleyemedi.");
    expect(failureText("SOME_NEW_CODE", t).what).toBe("Yayınlanırken bir şeyler ters gitti.");
    expect(failureText("UNKNOWN", t).next).toContain("düzenleyin");
  });
});
