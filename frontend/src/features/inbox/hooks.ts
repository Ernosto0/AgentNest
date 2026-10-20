import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type {
  Approval,
  ApprovedAnswer,
  AutomationPolicies,
  Conversation,
  ConversationDetail,
  PolicyItem,
  ReplyDraft,
  ReplyWithWarnings,
  SocialAccount,
} from "@/api/types";
import { newRequestId } from "@/features/commands/hooks";

export type AttentionFilter = "any" | "needs_approval" | "needs_human" | "failed";

export const conversationsKey = (ws: string, attention: AttentionFilter) =>
  ["conversations", ws, attention] as const;
export const conversationKey = (ws: string, id: string) => ["conversation", ws, id] as const;
const POLL_MS = 4000;

export function useConversations(ws: string, attention: AttentionFilter) {
  return useQuery<Conversation[], AppError>({
    queryKey: conversationsKey(ws, attention),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/conversations", {
            params: { path: { workspace_id: ws }, query: { attention } },
          }),
        )
      ).items,
    refetchInterval: POLL_MS,
  });
}

export function useConversation(ws: string, id: string) {
  return useQuery<ConversationDetail, AppError>({
    queryKey: conversationKey(ws, id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}", {
          params: { path: { workspace_id: ws, conversation_id: id } },
        }),
      ),
    refetchInterval: POLL_MS,
  });
}

export function useApproval(ws: string, approvalId: string | null) {
  return useQuery<Approval, AppError>({
    queryKey: ["approval", ws, approvalId],
    enabled: approvalId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/approvals/{approval_id}", {
          params: { path: { workspace_id: ws, approval_id: approvalId ?? "" } },
        }),
      ),
  });
}

export function useReplyDraft(ws: string, draftId: string | null) {
  return useQuery<ReplyDraft, AppError>({
    queryKey: ["reply-draft", ws, draftId],
    enabled: draftId !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reply-drafts/{draft_id}", {
          params: { path: { workspace_id: ws, draft_id: draftId ?? "" } },
        }),
      ),
  });
}

/** Everything that shows conversations, drafts, approvals or notifications moved. */
function useRefreshInbox(ws: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      ["conversations", "conversation", "approvals", "notifications", "approval", "reply-draft"].map(
        (name) => queryClient.invalidateQueries({ queryKey: [name, ws] }),
      ),
    );
}

export function useSubmitReply(ws: string, conversationId: string) {
  const refresh = useRefreshInbox(ws);
  return useMutation<ReplyWithWarnings, AppError, { text: string; fromDraftId?: string }>({
    mutationFn: ({ text, fromDraftId }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/replies", {
          params: { path: { workspace_id: ws, conversation_id: conversationId } },
          body: { text, client_request_id: newRequestId(), from_draft_id: fromDraftId ?? null },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useEditDraft(ws: string) {
  const refresh = useRefreshInbox(ws);
  return useMutation<
    ReplyWithWarnings,
    AppError,
    { draft: ReplyDraft; text: string; approve: boolean }
  >({
    mutationFn: ({ draft, text, approve }) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/reply-drafts/{draft_id}", {
          params: { path: { workspace_id: ws, draft_id: draft.id } },
          body: { text, expected_version: draft.version, approve },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useCancelDraft(ws: string) {
  const refresh = useRefreshInbox(ws);
  return useMutation<ReplyDraft, AppError, string>({
    mutationFn: (draftId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/reply-drafts/{draft_id}/cancel", {
          params: { path: { workspace_id: ws, draft_id: draftId } },
        }),
      ),
    onSettled: () => refresh(),
  });
}

export function useHandlingMode(ws: string, conversationId: string) {
  const refresh = useRefreshInbox(ws);
  return useMutation<Conversation, AppError, "takeover" | "release">({
    mutationFn: (action) =>
      unwrap(
        api.POST(
          action === "takeover"
            ? "/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/takeover"
            : "/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/release",
          { params: { path: { workspace_id: ws, conversation_id: conversationId } } },
        ),
      ),
    onSettled: () => refresh(),
  });
}

export function useSuggestReply(ws: string, conversationId: string) {
  const refresh = useRefreshInbox(ws);
  return useMutation<unknown, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/suggest-reply", {
          params: { path: { workspace_id: ws, conversation_id: conversationId } },
        }),
      ),
    onSettled: () => refresh(),
  });
}

// --- automation and the connection ---

export function useAutomation(ws: string) {
  return useQuery<AutomationPolicies, AppError>({
    queryKey: ["automation", ws],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/automation-policies", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useSaveAutomation(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<AutomationPolicies, AppError, PolicyItem[]>({
    mutationFn: (items) =>
      unwrap(
        api.PUT("/api/v1/workspaces/{workspace_id}/automation-policies", {
          params: { path: { workspace_id: ws } },
          body: { items },
        }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(["automation", ws], data);
      void queryClient.invalidateQueries({ queryKey: ["readiness", ws] });
    },
  });
}

export function useSocialAccounts(ws: string) {
  return useQuery<SocialAccount[], AppError>({
    queryKey: ["social-accounts", ws],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/social-accounts", {
            params: { path: { workspace_id: ws } },
          }),
        )
      ).items,
  });
}

export function useConnectMock(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<SocialAccount, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/social-accounts/mock", {
          params: { path: { workspace_id: ws } },
          body: {},
        }),
      ),
    onSuccess: () =>
      Promise.all(
        ["social-accounts", "readiness", "automation"].map((name) =>
          queryClient.invalidateQueries({ queryKey: [name, ws] }),
        ),
      ),
  });
}

export function useReconnectMock(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<SocialAccount, AppError, string>({
    mutationFn: (accountId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/social-accounts/{account_id}/reconnect", {
          params: { path: { workspace_id: ws, account_id: accountId } },
        }),
      ),
    onSuccess: () =>
      Promise.all(
        ["social-accounts", "readiness", "automation", "conversations"].map((name) =>
          queryClient.invalidateQueries({ queryKey: [name, ws] }),
        ),
      ),
  });
}

// --- approved answers ---

export function useAnswers(ws: string) {
  return useQuery<ApprovedAnswer[], AppError>({
    queryKey: ["answers", ws],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/approved-answers", {
            params: { path: { workspace_id: ws } },
          }),
        )
      ).items,
  });
}

export function useCreateAnswer(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<
    ApprovedAnswer,
    AppError,
    { title: string; intent: string; question: string; template: string; language: "tr" | "en" }
  >({
    mutationFn: ({ title, intent, question, template, language }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/approved-answers", {
          params: { path: { workspace_id: ws } },
          body: {
            title,
            intent,
            example_questions: [question],
            answer_template: template,
            language,
          },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["answers", ws] }),
  });
}

export function useArchiveAnswer(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<ApprovedAnswer, AppError, ApprovedAnswer>({
    mutationFn: (answer) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/approved-answers/{answer_id}", {
          params: { path: { workspace_id: ws, answer_id: answer.id } },
          body: { expected_version: answer.version, status: "archived" },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["answers", ws] }),
  });
}

export function useSaveAsAnswer(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<ApprovedAnswer, AppError, string>({
    mutationFn: (messageId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/approved-answers/from-message/{message_id}", {
          params: { path: { workspace_id: ws, message_id: messageId } },
          body: {},
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["answers", ws] }),
  });
}
