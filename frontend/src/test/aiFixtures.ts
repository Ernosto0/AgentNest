import type { Approval, AppNotification, Command } from "@/api/types";
import { WS_GOLKENT } from "./fixtures";

export const HASH = "a".repeat(64);

export function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: "a0000000-0000-4000-8000-000000000001",
    kind: "confirmation",
    action: "command.update_fact",
    status: "pending",
    summary: {
      label: "Aylık üyelik",
      key: "pricing.membership_monthly",
      category: "pricing",
      old_formatted: "6.000 ₺ / ay",
      new_formatted: "7.000 ₺ / ay",
      impact: { total: 0, items: [] },
    },
    payload_hash: HASH,
    subject: {
      type: "owner_command",
      id: "c0000000-0000-4000-8000-000000000001",
      version: 1,
      status: "awaiting_confirmation",
      link: { target: "owner_command", id: "c0000000-0000-4000-8000-000000000001" },
    },
    expires_at: "2026-10-15T12:30:00Z",
    execute_before: null,
    required_permission: "knowledge.verify",
    can_decide: true,
    is_simulated: false,
    created_at: "2026-10-15T12:00:00Z",
    decided_at: null,
    cancel_reason: null,
    ...overrides,
  };
}

export function command(overrides: Partial<Command> = {}): Command {
  return {
    id: "c0000000-0000-4000-8000-000000000001",
    status: "interpreting",
    raw_text: "Aylık üyelik artık 7.000 TL",
    command_type: null,
    result: null,
    clarification: null,
    approval: null,
    error_code: null,
    created_at: "2026-10-15T12:00:00Z",
    expires_at: null,
    completed_at: null,
    ...overrides,
  };
}

export function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n0000000-0000-4000-8000-000000000001",
    type: "knowledge.fact_changed",
    severity: "info",
    params: {
      fact_key: "pricing.membership_monthly",
      label: { tr: "Aylık üyelik", en: "Monthly membership" },
      change: "value_changed",
      old_display: "6.000 ₺ / ay",
      new_display: "7.000 ₺ / ay",
      version: 2,
    },
    subject_type: "business_fact",
    subject_id: "f0000000-0000-4000-8000-000000000001",
    is_simulated: false,
    read_at: null,
    created_at: "2026-10-15T12:05:00Z",
    ...overrides,
  };
}

export const BASE = `/api/v1/workspaces/${WS_GOLKENT}`;
