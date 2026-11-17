import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { components } from "@/api/schema";

export type LadderSuggestion = components["schemas"]["SuggestionOut"];
type DelegationChange = components["schemas"]["DelegationChange"];

/** Approval-ladder suggestions (D-02) that the owner can still act on. Owners only (the API says 403 otherwise). */
export function useLadderSuggestions(ws: string, enabled: boolean) {
  return useQuery<LadderSuggestion[], AppError>({
    queryKey: ["delegation-suggestions", ws],
    enabled,
    retry: false,
    queryFn: async () => (await unwrap(api.GET("/api/v1/workspaces/{workspace_id}/delegation-suggestions", { params: { path: { workspace_id: ws } } }))).items,
  });
}

/** Refresh what a confirmed suggestion changes: the list itself, the reply rules and what the activity feed shows. */
function useRefreshLadder(ws: string) {
  const client = useQueryClient();
  return () => Promise.all(["delegation-suggestions", "agent", "automation", "activity", "notifications", "readiness"].map((name) => client.invalidateQueries({ queryKey: [name, ws] })));
}

/** Step one: bind the owner's preview to the exact change the suggestion carries (the existing delegation preview). */
export function usePreviewLadder(ws: string, account: string) {
  return useMutation<components["schemas"]["DelegationPreview"], AppError, DelegationChange>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/delegation/preview", { params: { path: { workspace_id: ws, account_id: account } }, body })),
  });
}

/**
 * Step two: apply that same change (the existing delegation apply). ``onApplied`` runs before the
 * lists refetch, because the refetch removes the suggestion and so unmounts the card that asked.
 */
export function useApplyLadder(ws: string, account: string, onApplied: () => void) {
  const refresh = useRefreshLadder(ws);
  return useMutation<components["schemas"]["DelegationOut"], AppError, DelegationChange>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/delegation/apply", { params: { path: { workspace_id: ws, account_id: account } }, body })),
    onSuccess: () => {
      onApplied();
      return refresh();
    },
  });
}

export function useDismissLadder(ws: string) {
  const refresh = useRefreshLadder(ws);
  return useMutation<components["schemas"]["SuggestionDismissed"], AppError, string>({
    mutationFn: (id) => unwrap(api.POST("/api/v1/workspaces/{workspace_id}/delegation-suggestions/{suggestion_id}/dismiss", { params: { path: { workspace_id: ws, suggestion_id: id } } })),
    onSuccess: refresh,
  });
}
