import { describe, expect, it } from "vitest";
import enAi from "@/i18n/locales/en/ai.json";
import enCommon from "@/i18n/locales/en/common.json";
import trAi from "@/i18n/locales/tr/ai.json";
import trCommon from "@/i18n/locales/tr/common.json";
import {
  CLARIFY_QUESTIONS,
  LINK_TARGETS,
  PERIODS,
  RESULT_MESSAGE_KEYS,
  SUGGESTION_KEYS,
  UNSUPPORTED_REASONS,
  messageSuffix,
  type ResultLink,
  linkPath,
} from "./messages";

// `npm run i18n:check` verifies literal t("key") calls. The command texts are looked up by the
// run-time keys the API sends (`command.fact_updated` ...), so every key it can send is pinned.
const ACTIONS = [
  "command_update_fact",
  "command_update_brand_voice",
  "command_cancel_content",
  "reply_send",
  "content_publish",
];
const NOTIFICATION_TYPES = [
  "approval_requested",
  "approval_expired",
  "knowledge_fact_changed",
  "knowledge_fact_archived",
  "content_on_hold",
  "content_published",
  "content_failed",
  "unknown",
];
const API_ERROR_CODES = [
  "APPROVAL_ALREADY_DECIDED",
  "APPROVAL_EXPIRED",
  "APPROVAL_STALE",
  "FACT_NOT_USABLE",
  "FACT_CHANGED_MEANWHILE",
  "LLM_UNAVAILABLE",
  "LLM_OUTPUT_INVALID",
  "LLM_REFUSED",
  "LLM_BUDGET_EXCEEDED",
  "FORBIDDEN",
  "NOT_FOUND",
  "VALIDATION_FAILED",
];

function lookup(catalog: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);
}

describe.each([
  ["tr", trAi, trCommon],
  ["en", enAi, enCommon],
] as const)("%s catalog covers every key the API can send", (_language, ai, common) => {
  const has = (path: string) => typeof lookup(ai, path) === "string";

  it("command results", () => {
    for (const key of RESULT_MESSAGE_KEYS) {
      const plural = key === "pending_approvals";
      expect(plural ? has(`command.msg.${key}_one`) && has(`command.msg.${key}_other`) : has(`command.msg.${key}`), key).toBe(true);
    }
    expect(has("command.msg.pending_none")).toBe(true);
  });

  it("unsupported reasons, suggestions, links, periods and questions", () => {
    for (const reason of UNSUPPORTED_REASONS) expect(has(`command.unsupported.reason.${reason}`), reason).toBe(true);
    for (const key of SUGGESTION_KEYS) expect(has(`command.suggest.${key}`), key).toBe(true);
    for (const target of LINK_TARGETS) expect(has(`command.link.${target}`), target).toBe(true);
    expect(has("command.link.content_item")).toBe(true);
    for (const period of PERIODS) expect(has(`command.period.${period}`), period).toBe(true);
    for (const question of CLARIFY_QUESTIONS) expect(has(`command.clarify.${question}`), question).toBe(true);
  });

  it("approval actions, statuses, impact referrers and notification types", () => {
    for (const action of ACTIONS) expect(has(`approvals.action.${action}`), action).toBe(true);
    for (const status of ["pending", "approved", "rejected", "expired", "cancelled"]) {
      expect(has(`approvals.status.${status}`), status).toBe(true);
    }
    for (const referrer of ["reply_draft", "content_item", "approved_answer"]) {
      expect(has(`approvals.referrer.${referrer}`), referrer).toBe(true);
    }
    for (const type of NOTIFICATION_TYPES) expect(has(`notifications.type.${type}`), type).toBe(true);
  });

  it("the error codes the AI features raise", () => {
    for (const code of API_ERROR_CODES) {
      expect(typeof lookup(common, `errors.${code}.what`), code).toBe("string");
      expect(typeof lookup(common, `errors.${code}.next`), code).toBe("string");
    }
  });
});

describe("result helpers", () => {
  it("strips the namespace of a message key", () => {
    expect(messageSuffix("command.fact_updated")).toBe("fact_updated");
  });

  it("links are structured and map to app routes", () => {
    const link = (target: string, extra: Partial<ResultLink> = {}): ResultLink => ({ target, ...extra });
    expect(linkPath("w1", link("knowledge", { category: "pricing" }))).toBe("/w/w1/more/knowledge/pricing");
    expect(linkPath("w1", link("knowledge"))).toBe("/w/w1/more/knowledge");
    expect(linkPath("w1", link("approvals"))).toBe("/w/w1/approvals");
    expect(linkPath("w1", link("content"))).toBe("/w/w1/content");
    expect(linkPath("w1", link("content", { id: "c1" }))).toBe("/w/w1/content/c1");
    expect(linkPath("w1", link("inbox"))).toBe("/w/w1/inbox");
    expect(linkPath("w1", link("integrations"))).toBe("/w/w1/more");
  });
});
