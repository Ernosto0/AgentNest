import type { ActivityEntry, DailyReport, MetricItem, MetricItems, ReportMetric } from "@/api/types";
import { WS_GOLKENT } from "./fixtures";

export const REPORT_BASE = `/api/v1/workspaces/${WS_GOLKENT}/reports/daily`;
export const ACTIVITY_PATH = `/api/v1/workspaces/${WS_GOLKENT}/activity`;

export function metric(
  key: string,
  value: number | null,
  section: string,
  date: string,
  overrides: Partial<ReportMetric> = {},
): ReportMetric {
  return {
    key,
    value,
    kind: key.endsWith("_now") ? "snapshot" : "period",
    section,
    breakdown: null,
    link: {
      api: `${REPORT_BASE}/${date}/metrics/${key}`,
      route: `/w/${WS_GOLKENT}/more/reports/${date}/${key}`,
    },
    screen_link: null,
    ...overrides,
  };
}

export function report(date: string, overrides: Partial<DailyReport> = {}): DailyReport {
  const metrics = [
    metric("inbound_messages", 15, "messages", date),
    metric("replies_sent", 0, "messages", date),
    metric("median_first_response_minutes", 6.5, "messages", date),
    metric("pending_approvals_now", 4, "approvals", date, {
      breakdown: { "reply.send": 4 },
      screen_link: { api: `/api/v1/workspaces/${WS_GOLKENT}/approvals?status=pending`, route: `/w/${WS_GOLKENT}/approvals` },
    }),
    metric("content_published", 0, "content", date),
    metric("content_failed", 0, "content", date),
    metric("fact_changes", 0, "knowledge", date),
    metric("integration_errors", 2, "problems", date),
  ];
  return {
    local_date: date,
    timezone: "Europe/Istanbul",
    period_start: `${date}T00:00:00Z`,
    period_end: `${date}T21:00:00Z`,
    generated_at: `${date}T21:00:00Z`,
    is_partial: false,
    definitions_version: "1",
    has_simulated_data: false,
    metrics,
    summary: {
      empty: false,
      text: "",
      sections: [
        { section: "messages", title: "Mesajlar", lines: [] },
        { section: "approvals", title: "Onaylar", lines: [] },
        { section: "problems", title: "Sorunlar", lines: [] },
      ],
    },
    ...overrides,
  };
}

export function item(n: number, overrides: Partial<MetricItem> = {}): MetricItem {
  const id = `c0000000-0000-4000-8000-00000000000${n}`;
  return {
    kind: "message",
    id,
    label: `musteri_${n}`,
    occurred_at: "2026-10-14T09:30:00Z",
    is_simulated: false,
    measure: null,
    link: { api: null, route: `/w/${WS_GOLKENT}/inbox/${id}` },
    ...overrides,
  };
}

export function metricItems(
  key: string,
  value: number,
  items: MetricItem[],
  next_cursor: string | null = null,
): MetricItems {
  return { key, value, items, next_cursor };
}

export function entry(n: number, overrides: Partial<ActivityEntry> = {}): ActivityEntry {
  return {
    id: `e0000000-0000-4000-8000-00000000000${n}`,
    action: "reply.sent",
    group: "replies",
    occurred_at: "2026-10-15T12:00:00Z",
    actor: { type: "user", label: "Demo Sahip" },
    text: "Yanıt gönderildi",
    resource: {
      type: "reply_draft",
      id: `d0000000-0000-4000-8000-00000000000${n}`,
      label: "ayse_k",
      link: `/w/${WS_GOLKENT}/inbox/c1000000-0000-4000-8000-000000000001`,
    },
    is_simulated: false,
    ...overrides,
  };
}
