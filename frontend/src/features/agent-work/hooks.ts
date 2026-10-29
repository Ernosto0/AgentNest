import { newRequestId } from "@/features/commands/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { agentKey, type Schema } from "@/features/agent/hooks";
import type { AppError } from "@/api/errors";

export function useWorkThreads(ws: string, account: string, source?: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "threads", source],
    enabled: !!account,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/threads", {
          params: {
            path: { workspace_id: ws, account_id: account },
            query: { source_ref: source },
          },
        }),
      ),
  });
}
export function useQuestions(ws: string, account: string, cursor?: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "questions", cursor],
    enabled: !!account,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/owner-questions", {
          params: { path: { workspace_id: ws, account_id: account }, query: { cursor, limit: 20 } },
        }),
      ),
  });
}
export function useQuestion(ws: string, account: string, id: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "question", id],
    enabled: !!account && !!id,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/owner-questions/{question_id}",
          { params: { path: { workspace_id: ws, account_id: account, question_id: id } } },
        ),
      ),
  });
}
export function useQuestionAnswers(ws: string, account: string, id: string, cursor?: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "answers", id, cursor],
    enabled: !!account && !!id,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/owner-questions/{question_id}/answers",
          {
            params: {
              path: { workspace_id: ws, account_id: account, question_id: id },
              query: { cursor, limit: 20 },
            },
          },
        ),
      ),
  });
}
export function useRefreshWork(ws: string) {
  const client = useQueryClient();
  return async () => {
    // Remove bodies before refetch: correction/erasure must not leave previous cached previews visible.
    const filters = [
      { queryKey: ["agent-private", ws] },
      { queryKey: ["agent-action", ws] },
      {
        predicate: (q: { queryKey: readonly unknown[] }) =>
          q.queryKey[0] === "agent" &&
          q.queryKey[1] === ws &&
          ["question", "questions", "answers"].includes(String(q.queryKey[3])),
      },
    ];
    for (const filter of filters) client.removeQueries({ ...filter, type: "inactive" });
    await Promise.all(filters.map((filter) => client.resetQueries({ ...filter, type: "active" })));
    await Promise.all(
      [
        "agent",
        "conversation",
        "conversations",
        "approvals",
        "approval",
        "activity",
        "report",
        "notifications",
        "reply-draft",
      ].map((name) => client.invalidateQueries({ queryKey: [name, ws] })),
    );
  };
}
export function useAnswerQuestion(ws: string, account: string, id: string) {
  const refresh = useRefreshWork(ws);
  return useMutation<Schema<"AnswerOut">, AppError, Schema<"AnswerRequest">>({
    mutationFn: (body) =>
      unwrap(
        api.POST(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/owner-questions/{question_id}/answer",
          { params: { path: { workspace_id: ws, account_id: account, question_id: id } }, body },
        ),
      ),
    onSettled: refresh,
  });
}
export function useMemory(ws: string, account: string, customer: string, cursor?: string) {
  return useQuery({
    queryKey: ["agent-private", ws, account, customer, "memory", cursor],
    enabled: !!account && !!customer,
    gcTime: 0,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/customers/{customer_id}/memory",
          {
            params: {
              path: { workspace_id: ws, account_id: account, customer_id: customer },
              query: { cursor, limit: 20 },
            },
          },
        ),
      ),
  });
}
export function useMemorySources(ws: string, account: string, customer: string, cursor?: string) {
  return useQuery({
    queryKey: ["agent-private", ws, account, customer, "sources", cursor],
    enabled: !!account && !!customer,
    gcTime: 0,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/customers/{customer_id}/sources",
          {
            params: {
              path: { workspace_id: ws, account_id: account, customer_id: customer },
              query: { cursor, limit: 20 },
            },
          },
        ),
      ),
  });
}
export function useChangeMemory(ws: string, account: string, customer: string) {
  const refresh = useRefreshWork(ws);
  return useMutation({
    mutationFn: (input: { id: string; version: number; body?: string }) =>
      input.body === undefined
        ? unwrap(
            api.POST(
              "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/customers/{customer_id}/memory/{memory_id}/forget",
              {
                params: {
                  path: {
                    workspace_id: ws,
                    account_id: account,
                    customer_id: customer,
                    memory_id: input.id,
                  },
                },
              },
            ),
          )
        : unwrap(
            api.POST(
              "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/customers/{customer_id}/memory/{memory_id}/correct",
              {
                params: {
                  path: {
                    workspace_id: ws,
                    account_id: account,
                    customer_id: customer,
                    memory_id: input.id,
                  },
                },
                body: { expected_version: input.version, body: input.body },
              },
            ),
          ),
    onSettled: refresh,
  });
}
export function useComments(ws: string, account: string, cursor?: string, thread?: string) {
  const params = {
    path: { workspace_id: ws, account_id: account, thread_id: thread ?? "" },
    query: { cursor, limit: 20 },
  };
  return useQuery({
    queryKey: [...agentKey(ws, account), "comments", thread, cursor],
    enabled: !!account,
    refetchInterval: 4000,
    queryFn: () =>
      thread
        ? unwrap(
            api.GET(
              "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments/threads/{thread_id}",
              { params },
            ),
          )
        : unwrap(
            api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments", { params }),
          ),
  });
}
export function useCommentMedia(ws: string, account: string, id: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "media", id],
    enabled: !!account && !!id,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments/media/{media_id}",
          { params: { path: { workspace_id: ws, account_id: account, media_id: id } } },
        ),
      ),
  });
}
export function useThreadControl(ws: string, account: string) {
  const refresh = useRefreshWork(ws);
  return useMutation({
    mutationFn: (input: { id: string; version: number; mode: "agent" | "human" }) =>
      unwrap(
        api.POST(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/threads/{thread_id}/control",
          {
            params: { path: { workspace_id: ws, account_id: account, thread_id: input.id } },
            body: {
              expected_version: input.version,
              handling_mode: input.mode,
              client_request_id: newRequestId(),
            },
          },
        ),
      ),
    onSettled: refresh,
  });
}
export function useTask(ws: string, account: string, id: string) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "task", id],
    enabled: !!account && !!id,
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/tasks/{task_id}", {
          params: { path: { workspace_id: ws, account_id: account, task_id: id } },
        }),
      ),
  });
}
export function useAnswerTask(ws: string, account: string, id: string) {
  const refresh = useRefreshWork(ws);
  return useMutation({
    mutationFn: (body: Schema<"TaskAnswer">) =>
      unwrap(
        api.POST(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/tasks/{task_id}/answers",
          { params: { path: { workspace_id: ws, account_id: account, task_id: id } }, body },
        ),
      ),
    onSettled: refresh,
  });
}
export function useExactAction(ws: string, id: string, enabled = true) {
  return useQuery({
    queryKey: ["agent-action", ws, id],
    enabled: enabled && !!id,
    retry: false,
    gcTime: 0,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/agent-actions/{action_id}", {
          params: { path: { workspace_id: ws, action_id: id } },
        }),
      ),
  });
}
export function useSelections(
  ws: string,
  account: string,
  kind: "media" | "content",
  cursor?: string,
) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "selections", kind, cursor],
    enabled: !!account,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent/task-selections", {
          params: {
            path: { workspace_id: ws, account_id: account },
            query: { kind, cursor, limit: 20 },
          },
        }),
      ),
  });
}
export function useManualModeration(ws: string, account: string, comment: string) {
  const refresh = useRefreshWork(ws);
  return useMutation({
    mutationFn: (body: Schema<"ManualModeration">) =>
      unwrap(
        api.POST(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments/{comment_id}/moderate",
          {
            params: { path: { workspace_id: ws, account_id: account, comment_id: comment } },
            body,
          },
        ),
      ),
    onSettled: refresh,
  });
}
export function useModerationOperations(
  ws: string,
  account: string,
  comment: string,
  cursor?: string,
) {
  return useQuery({
    queryKey: [...agentKey(ws, account), "manual-operations", comment, cursor],
    refetchInterval: 4000,
    queryFn: () =>
      unwrap(
        api.GET(
          "/api/v1/workspaces/{workspace_id}/accounts/{account_id}/comments/{comment_id}/moderation-operations",
          { params: { path: { workspace_id: ws, account_id: account, comment_id: comment }, query:{cursor,limit:20} } },
        ),
      ),
  });
}
