import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { MetricItems, MissedCustomerReport } from "@/api/types";

/** `week` is a local Monday (`YYYY-MM-DD`); null asks for this week so far, computed live. */
export const missedKey = (ws: string, week: string | null) => ["missed-report", ws, week ?? "current"] as const;
export const missedItemsKey = (ws: string, week: string, key: string) => ["missed-items", ws, week, key] as const;

export function useMissedReport(ws: string, week: string | null) {
  return useQuery<MissedCustomerReport, AppError>({
    queryKey: missedKey(ws, week),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reports/missed-customers", {
          params: { path: { workspace_id: ws }, query: week ? { week_start: week } : {} },
        }),
      ),
  });
}

/** The conversations or messages behind one number, newest first, one page at a time. */
export function useMissedItems(ws: string, week: string, key: string) {
  return useInfiniteQuery<MetricItems, AppError, { pages: MetricItems[] }, readonly unknown[], string | null>({
    queryKey: missedItemsKey(ws, week, key),
    initialPageParam: null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reports/missed-customers/{week_start}/metrics/{key}", {
          params: {
            path: { workspace_id: ws, week_start: week, key },
            query: pageParam ? { cursor: pageParam } : {},
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}
