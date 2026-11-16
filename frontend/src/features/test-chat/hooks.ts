import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { components } from "@/api/schema";

type Schemas = components["schemas"];
export type TestChatState = Schemas["AssistantChatOut"];
export type TestChatTurn = Schemas["AssistantChatTurnOut"];
export type TestChatDraft = Schemas["AssistantChatDraftOut"];

/** The server limits a message to 500 characters (AssistantChatMessageIn). */
export const MAX_MESSAGE_CHARS = 500;
/** How often to ask again while a draft is still being written. */
export const POLL_MS = 1500;

export const testChatKey = (workspaceId: string) => ["test-chat", workspaceId] as const;

export const hasPending = (chat: TestChatState | undefined) => chat?.items.some((turn) => turn.status === "pending") ?? false;

/** The caller's own test chat. Polls only while a turn is pending, then stops. */
export function useTestChat(workspaceId: string) {
  return useQuery<TestChatState, AppError>({
    queryKey: testChatKey(workspaceId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/workspaces/{workspace_id}/assistant/test-chat", { params: { path: { workspace_id: workspaceId } } })),
    refetchInterval: (query) => (hasPending(query.state.data) ? POLL_MS : false),
    retry: (count, error) => !(error instanceof AppError && error.status < 500) && count < 2,
  });
}

/** Send one test customer message (202, pending). The turn is added at once; polling fetches the draft. */
export function useSendTestMessage(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<TestChatTurn, AppError, string>({
    mutationFn: (text) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/assistant/test-chat/messages", {
          params: { path: { workspace_id: workspaceId } },
          body: { text },
        }),
      ),
    onSuccess: (turn) => {
      client.setQueryData<TestChatState>(testChatKey(workspaceId), (old) =>
        old
          ? {
              ...old,
              items: [...old.items.filter((item) => item.id !== turn.id), turn],
              remaining_this_hour: Math.max(0, old.remaining_this_hour - 1),
              remaining_today: Math.max(0, old.remaining_today - 1),
            }
          : old,
      );
      return client.invalidateQueries({ queryKey: testChatKey(workspaceId) });
    },
  });
}

/** Clear the caller's test chat. It does not give back any of the rate limit. */
export function useResetTestChat(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<Schemas["AssistantChatResetOut"], AppError, void>({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/workspaces/{workspace_id}/assistant/test-chat/reset", { params: { path: { workspace_id: workspaceId } } })),
    onSuccess: () => {
      client.setQueryData<TestChatState>(testChatKey(workspaceId), (old) => (old ? { ...old, items: [] } : old));
      return client.invalidateQueries({ queryKey: testChatKey(workspaceId) });
    },
  });
}
