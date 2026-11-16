import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { Approval, Command, Me } from "@/api/types";
import { meKey } from "@/features/auth/hooks";
import { notePushOpportunity } from "@/pwa/push";

export const commandKey = (workspaceId: string, commandId: string) =>
  ["command", workspaceId, commandId] as const;
export const approvalsKey = (workspaceId: string) => ["approvals", workspaceId] as const;
export const notificationsKey = (workspaceId: string) => ["notifications", workspaceId] as const;

/** A request id for idempotent creation: a resubmission returns the same command. */
export function newRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Statuses in which the server is still working: the UI polls (api-design.md §1). */
const WORKING = new Set<Command["status"]>(["interpreting", "executing"]);

export function useCommand(workspaceId: string, commandId: string | null) {
  return useQuery<Command, AppError>({
    queryKey: commandKey(workspaceId, commandId ?? "none"),
    enabled: commandId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/commands/{command_id}", {
          params: { path: { workspace_id: workspaceId, command_id: commandId ?? "" } },
        }),
      ),
    refetchInterval: (query) => (query.state.data && WORKING.has(query.state.data.status) ? 1000 : false),
  });
}

/** After anything that can change facts or approvals, refresh what shows them. */
function useRefreshAfterDecision(workspaceId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all(
      [
        ["facts", workspaceId],
        ["fact-candidates", workspaceId],
        ["fact-versions", workspaceId],
        ["readiness", workspaceId],
        // A decision can schedule, publish-queue or cancel content.
        ["content-items", workspaceId],
        ["content-item", workspaceId],
        approvalsKey(workspaceId),
        notificationsKey(workspaceId),
        ["command", workspaceId],
      ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
  };
}

export function useSubmitCommand(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<Command, AppError, string>({
    mutationFn: (text) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/commands", {
          params: { path: { workspace_id: workspaceId } },
          body: { text, client_request_id: newRequestId() },
        }),
      ),
    onSuccess: (command) => queryClient.setQueryData(commandKey(workspaceId, command.id), command),
  });
}

export function useAnswerClarification(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<Command, AppError, { commandId: string; optionId: string }>({
    mutationFn: ({ commandId, optionId }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/commands/{command_id}/clarification", {
          params: { path: { workspace_id: workspaceId, command_id: commandId } },
          body: { option_id: optionId },
        }),
      ),
    onSuccess: (command) => queryClient.setQueryData(commandKey(workspaceId, command.id), command),
  });
}

export function useCancelCommand(workspaceId: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshAfterDecision(workspaceId);
  return useMutation<Command, AppError, string>({
    mutationFn: (commandId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/commands/{command_id}/cancel", {
          params: { path: { workspace_id: workspaceId, command_id: commandId } },
        }),
      ),
    onSuccess: async (command) => {
      queryClient.setQueryData(commandKey(workspaceId, command.id), command);
      await refresh();
    },
  });
}

export interface DecisionInput {
  approval: Approval;
  decision: "approve" | "reject";
  note?: string;
}

/** Decide with the hash the user was shown: any change since then is a 409 `APPROVAL_STALE`. */
export function useDecideApproval(workspaceId: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshAfterDecision(workspaceId);
  return useMutation<Approval, AppError, DecisionInput>({
    mutationFn: ({ approval, decision, note }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/approvals/{approval_id}/decision", {
          params: { path: { workspace_id: workspaceId, approval_id: approval.id } },
          body: { decision, payload_hash: approval.payload_hash, note: note ?? null },
        }),
      ),
    onSuccess: (_approval, { decision }) => {
      // The first approval is when the app offers phone notifications (not on first load).
      const userId = queryClient.getQueryData<Me | null>(meKey)?.user.id;
      if (decision === "approve" && userId) notePushOpportunity(userId, workspaceId);
    },
    // Success or a 409, the server state moved: show what it is now.
    onSettled: () => refresh(),
  });
}

export function useApprovals(workspaceId: string) {
  return useQuery<Approval[], AppError>({
    queryKey: approvalsKey(workspaceId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/approvals", {
            params: { path: { workspace_id: workspaceId }, query: { limit: 100 } },
          }),
        )
      ).items,
    refetchInterval: 15_000,
  });
}
