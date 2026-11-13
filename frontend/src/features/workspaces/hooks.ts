import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { Workspace, WorkspacePatchBody } from "@/api/types";

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

/**
 * Owner-only partial update (PATCH /workspaces/{id}, `workspace.manage`). The server validates
 * the timezone and name; the cached workspace and the membership names follow the response.
 */
export function useUpdateWorkspace(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<Workspace, AppError, WorkspacePatchBody>({
    mutationFn: (body) =>
      unwrap(api.PATCH("/api/v1/workspaces/{workspace_id}", { params: { path: { workspace_id: workspaceId } }, body })),
    onSuccess: (workspace) => {
      queryClient.setQueryData(["workspace", workspaceId], workspace);
      // The switcher and picker show the name from the membership list on /auth/me.
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
