import { useInfiniteQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { ActivityPage } from "@/api/types";

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

export const activityKey = (ws: string, group: ActivityGroup | null) =>
  ["activity", ws, group ?? "all"] as const;

/** The audit feed, newest first, one page at a time (opaque cursor from the server). */
export function useActivity(ws: string, group: ActivityGroup | null) {
  return useInfiniteQuery<ActivityPage, AppError, { pages: ActivityPage[] }, readonly unknown[], string | null>({
    queryKey: activityKey(ws, group),
    initialPageParam: null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/activity", {
          params: {
            path: { workspace_id: ws },
            query: { ...(group ? { type: group } : {}), ...(pageParam ? { cursor: pageParam } : {}) },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}
