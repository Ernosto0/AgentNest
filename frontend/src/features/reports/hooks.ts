import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { DailyReport, MetricItems } from "@/api/types";

/** `date` is a local day (`YYYY-MM-DD`); null asks for today, computed live by the server. */
export const reportKey = (ws: string, date: string | null, snapshot: string | null = null) =>
  ["report", ws, date ?? "today", snapshot] as const;
export const metricItemsKey = (ws: string, date: string, key: string, snapshot: string | null = null) =>
  ["report-items", ws, date, key, snapshot] as const;

export function useDailyReport(ws: string, date: string | null, snapshot: string | null = null) {
  return useQuery<DailyReport, AppError>({
    queryKey: reportKey(ws, date, snapshot),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reports/daily", {
          params: {
            path: { workspace_id: ws },
            query: { ...(date ? { date } : {}), ...(snapshot ? { snapshot_id: snapshot } : {}) },
          },
        }),
      ),
  });
}

/** Compute the day again and store it; the answer replaces what the screen shows. */
export function useGenerateReport(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<DailyReport, AppError, string>({
    mutationFn: (date) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/reports/daily/generate", {
          params: { path: { workspace_id: ws } },
          body: { date },
        }),
      ),
    onSuccess: (report, date) => {
      queryClient.setQueryData(reportKey(ws, date), report);
      queryClient.invalidateQueries({ queryKey: ["report", ws] });
      queryClient.invalidateQueries({ queryKey: ["report-items", ws] });
    },
  });
}

/** The records behind one number, newest first, one page at a time. */
export function useMetricItems(ws: string, date: string, key: string, snapshot: string | null = null) {
  return useInfiniteQuery<MetricItems, AppError, { pages: MetricItems[] }, readonly unknown[], string | null>({
    queryKey: metricItemsKey(ws, date, key, snapshot),
    initialPageParam: null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reports/daily/{local_date}/metrics/{key}", {
          params: {
            path: { workspace_id: ws, local_date: date, key },
            query: {
              ...(pageParam ? { cursor: pageParam } : {}),
              ...(snapshot ? { snapshot_id: snapshot } : {}),
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}
