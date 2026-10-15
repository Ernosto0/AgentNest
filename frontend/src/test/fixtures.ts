import type { Me, Workspace } from "@/api/types";

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
      disclosure_enabled: true,
      disclosure_text: { tr: "", en: "" },
      daily_report_hour: 20,
      publish_max_delay_minutes: 360,
    },
    created_at: "2026-10-15T12:00:00Z",
    ...overrides,
  };
}
