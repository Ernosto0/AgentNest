import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { ContentItem } from "@/api/types";

const HOME_LIST = 3;

/** The next scheduled posts, soonest first (the scheduled list is already sorted that way). */
export function useUpcomingPosts(ws: string) {
  return useQuery<ContentItem[], AppError>({
    queryKey: ["content-items", ws, "home-upcoming"],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/content-items", {
            params: { path: { workspace_id: ws }, query: { tab: "scheduled", limit: HOME_LIST } },
          }),
        )
      ).items,
    refetchInterval: 60_000,
  });
}

/** The most recent posts that failed for good, newest first. */
export function useRecentFailures(ws: string) {
  return useQuery<ContentItem[], AppError>({
    queryKey: ["content-items", ws, "home-failed"],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/content-items", {
            params: { path: { workspace_id: ws }, query: { status: "failed", limit: HOME_LIST } },
          }),
        )
      ).items,
    refetchInterval: 60_000,
  });
}
