import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { Workspace } from "@/api/types";

export function useWorkspace(workspaceId: string) {
  return useQuery<Workspace, AppError>({
    queryKey: ["workspace", workspaceId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
    // A missing or foreign workspace is a definite answer: do not retry it.
    retry: (count, error) => !(error instanceof AppError && error.status < 500) && count < 2,
  });
}
