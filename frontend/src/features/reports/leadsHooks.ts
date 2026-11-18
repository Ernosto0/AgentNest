import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { LeadList } from "@/api/types";

export function useLeads(ws: string, from: string, to: string) {
  return useInfiniteQuery<LeadList, AppError, { pages: LeadList[] }, readonly unknown[], number>({
    queryKey: ["leads", ws, from, to],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/leads", {
      params: { path: { workspace_id: ws }, query: { from, to, offset: pageParam, limit: 50 } },
    })),
    getNextPageParam: (last) => last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined,
  });
}

export function useExportLeads(ws: string) {
  return useMutation<{ count: number; truncated: boolean }, AppError, { from: string; to: string; total: number }>({
    mutationFn: async ({ from, to, total }) => {
      const result = await api.POST("/api/v1/workspaces/{workspace_id}/leads/export", {
        params: { path: { workspace_id: ws } }, body: { from, to }, parseAs: "blob",
      }).catch(() => { throw new AppError("NETWORK_ERROR", 0); });
      // openapi-fetch has received and parsed the whole blob before success is possible.
      const blob = await unwrap(Promise.resolve(result));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      try {
        a.href = url;
        a.download = `leads-${from}_${to}.csv`;
        document.body.appendChild(a);
        a.click();
      } finally {
        a.remove();
        URL.revokeObjectURL(url);
      }
      const header = result.response.headers.get("X-Row-Count");
      return {
        count: header !== null && /^\d+$/.test(header) ? Number(header) : total,
        truncated: result.response.headers.get("X-Truncated") === "true",
      };
    },
  });
}
