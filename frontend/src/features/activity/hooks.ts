import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { ActivityLevel, ActivityPage, ActivitySummary } from "@/api/types";

/** The groups of the `type` filter, in the order the chips show them (api-design.md 2.8). */
export const ACTIVITY_GROUPS = [
  "messages",
  "replies",
  "approvals",
  "content",
  "knowledge",
  "commands",
  "accounts",
  "members",
  "system",
] as const;
export type ActivityGroup = (typeof ACTIVITY_GROUPS)[number];

export function isActivityGroup(value: unknown): value is ActivityGroup {
  return typeof value === "string" && (ACTIVITY_GROUPS as readonly string[]).includes(value);
}

/** Outcome filter choices; each maps to the server's `level` values. */
export const OUTCOMES = ["problems", "failure", "warning", "success"] as const;
export type Outcome = (typeof OUTCOMES)[number];
export const OUTCOME_LEVELS: Record<Outcome, ActivityLevel[]> = {
  problems: ["failure", "warning"],
  failure: ["failure"],
  warning: ["warning"],
  success: ["success"],
};

export function isOutcome(value: unknown): value is Outcome {
  return typeof value === "string" && (OUTCOMES as readonly string[]).includes(value);
}

export interface ActivityFilters {
  group: ActivityGroup | null;
  outcome: Outcome | null;
  /** A local day on the workspace clock (YYYY-MM-DD). */
  day: string | null;
  /** Include routine bookkeeping entries (off by default). */
  technical: boolean;
  /** Show only the entries of one flow; the other filters do not apply then. */
  flow: string | null;
}

export const PAGE_SIZE = 50;

export const activityKey = (ws: string, filters: ActivityFilters) => ["activity", ws, filters] as const;

/** The audit feed, newest first, one page at a time (opaque cursor from the server). */
export function useActivity(ws: string, filters: ActivityFilters) {
  const query = filters.flow
    ? { correlation: filters.flow, include_routine: true }
    : {
        ...(filters.group ? { type: filters.group } : {}),
        ...(filters.outcome ? { level: OUTCOME_LEVELS[filters.outcome] } : {}),
        ...(filters.day ? { date: filters.day } : {}),
        include_routine: filters.technical,
      };
  return useInfiniteQuery<ActivityPage, AppError, { pages: ActivityPage[] }, readonly unknown[], string | null>({
    queryKey: activityKey(ws, filters),
    initialPageParam: null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/activity", {
          params: {
            path: { workspace_id: ws },
            query: { ...query, limit: PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export const SUMMARY_DAYS = 7;

/** Counts over the last local days, computed by the server over the whole history. */
export function useActivitySummary(ws: string) {
  return useQuery<ActivitySummary, AppError>({
    queryKey: ["activity", ws, "summary", SUMMARY_DAYS],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/activity/summary", {
          params: { path: { workspace_id: ws }, query: { days: SUMMARY_DAYS } },
        }),
      ),
  });
}
