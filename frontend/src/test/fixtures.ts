import type { Fact, FactCandidate, Me, Readiness, TemplateItem, Workspace } from "@/api/types";

export const WS_GOLKENT = "11111111-1111-4111-8111-111111111111";
export const WS_HARBOR = "22222222-2222-4222-8222-222222222222";
export const WS_PRIVATE = "33333333-3333-4333-8333-333333333333";

export const ME: Me = {
  user: {
    id: "99999999-9999-4999-8999-999999999999",
    email: "owner@demo.local",
    display_name: "Demo Sahip",
    ui_locale: "tr",
  },
  csrf_token: "csrf-token-for-tests",
  memberships: [
    { workspace_id: WS_GOLKENT, workspace_name: "Gölkent Fitness", role: "owner", is_demo: true },
    { workspace_id: WS_HARBOR, workspace_name: "Harbor Pilates", role: "manager", is_demo: true },
    { workspace_id: WS_PRIVATE, workspace_name: "Real Gym", role: "owner", is_demo: false },
  ],
};

export function workspace(id: string, overrides: Partial<Workspace> = {}): Workspace {
  const member = ME.memberships.find((m) => m.workspace_id === id);
  return {
    id,
    name: member?.workspace_name ?? "Unknown",
    slug: "slug",
    business_category: "gym",
    market: "tr",
    default_locale: "tr",
    reply_languages: ["tr"],
    timezone: "Europe/Istanbul",
    currency: "TRY",
    is_demo: member?.is_demo ?? false,
    status: "active",
    settings: {
      automation_reviewed_at: null,
      disclosure_enabled: true,
      disclosure_text: { tr: "", en: "" },
      daily_report_hour: 20,
      publish_max_delay_minutes: 1440,
    },
    created_at: "2026-10-15T12:00:00Z",
    ...overrides,
  };
}

export function fact(overrides: Partial<Fact> = {}): Fact {
  return {
    kind: "fact",
    id: "f0000000-0000-4000-8000-000000000001",
    key: "pricing.membership_monthly",
    category: "pricing",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    value_type: "money",
    value: { amount: "6000.00", currency: "TRY", unit: "month" },
    display: "6.000 ₺ / ay",
    status: "verified",
    state: "verified",
    criticality: "critical",
    current_version: 1,
    valid_from: null,
    valid_until: null,
    last_verified_at: "2026-10-12T09:00:00Z",
    last_verified_by_name: null,
    source_type: "seed",
    usable: true,
    open_candidates_count: 0,
    ...overrides,
  };
}

export function templateItem(overrides: Partial<TemplateItem> = {}): TemplateItem {
  return {
    identifier: "pricing.membership_monthly",
    key: "pricing.membership_monthly",
    pattern: null,
    category: "pricing",
    label: { tr: "Aylık üyelik", en: "Monthly membership" },
    description: { tr: "Aylık üyelik ücreti.", en: "The monthly membership price." },
    value_types: ["money"],
    criticality: "critical",
    required_for: null,
    required_group: null,
    required_when: null,
    allowed_values: [],
    status: "verified",
    fact_ids: [],
    ...overrides,
  };
}

export function candidate(overrides: Partial<FactCandidate> = {}): FactCandidate {
  return {
    kind: "candidate",
    id: "c0000000-0000-4000-8000-000000000001",
    fact_key: "pricing.membership_monthly",
    fact_id: "f0000000-0000-4000-8000-000000000001",
    fact_label: { tr: "Aylık üyelik", en: "Monthly membership" },
    value_type: "money",
    proposed_value: { amount: "5500.00", currency: "TRY", unit: "month" },
    proposed_display: "5.500 ₺ / ay",
    current_display: "6.000 ₺ / ay",
    relation: "discrepancy",
    status: "pending",
    source_type: "pasted_text",
    source_excerpt: "Instagram bio: Aylık üyelik 5.500 TL",
    proposed_by_name: null,
    created_at: "2026-10-15T12:00:00Z",
    resolved_at: null,
    ...overrides,
  };
}

export const READINESS: Readiness = {
  level: "ready_for_drafts",
  requirements: [
    { code: "business_name", required_for: "drafts", satisfied: true, status: "ok", link: { target: "knowledge", category: "identity", key: "identity.business_name" }, missing_keys: [] },
    { code: "booking_instructions", required_for: "ready", satisfied: false, status: "missing", link: { target: "knowledge", category: "booking", key: "booking.instructions" }, missing_keys: ["booking.instructions"] },
    { code: "account_connected", required_for: "ready", satisfied: false, status: "not_connected", link: { target: "integrations", category: null, key: null }, missing_keys: [] },
  ],
};
