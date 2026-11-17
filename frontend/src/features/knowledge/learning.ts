import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { components } from "@/api/schema";

export type LearnedMonth = components["schemas"]["LearnedMonth"];

/** Facts the owner verified from their own answers this calendar month (D-05). */
export const learningKey = (workspaceId: string) => ["learning-month", workspaceId] as const;

export function useLearnedMonth(workspaceId: string) {
  return useQuery<LearnedMonth, AppError>({
    queryKey: learningKey(workspaceId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/learning/month", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
  });
}
