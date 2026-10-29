import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { Invite, Member, PendingInvite, Role, SocialAccount, SystemHealth } from "@/api/types";
import { useCurrentWorkspace } from "@/features/workspaces/context";

export const systemHealthKey = (ws: string) => ["system-health", ws] as const;

const membersKey = (ws: string) => ["members", ws] as const;
const invitesKey = (ws: string) => ["invites", ws] as const;

const MEMBER_QUERY_KEYS = ["members", "invites"];

/** The health panel (owner and manager): counts and codes of the last 24 hours. */
export function useSystemHealth(ws: string) {
  return useQuery<SystemHealth, AppError>({
    queryKey: systemHealthKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/system-health", {
          params: { path: { workspace_id: ws } },
        }),
      ),
    retry: false,
  });
}

/** Disconnect the account; everything that reads its status is refreshed. */
export function useDisconnectAccount(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<SocialAccount, AppError, { accountId: string; deleteConversationData: boolean }>({
    mutationFn: ({ accountId, deleteConversationData }) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/social-accounts/{account_id}/disconnect", {
          params: { path: { workspace_id: ws, account_id: accountId } },
          body: { delete_conversation_data: deleteConversationData },
        }),
      ),
    onSuccess: (_, { deleteConversationData }) => {
      if (deleteConversationData) {
        // Erased history must not flash from cache when another screen mounts.
        for (const name of [
          "conversations", "conversation", "reply-draft", "approvals", "approval",
          "answers", "report", "report-items",
        ]) {
          queryClient.removeQueries({ queryKey: [name, ws] });
        }
      }
      return Promise.all(
        [
          "agent", "social-accounts", "readiness", "automation", "system-health", "conversations",
          "conversation", "reply-draft", "approvals", "approval", "content-items",
          "content-item", "notifications", "answers", "activity", "report", "report-items",
        ].map((name) =>
          queryClient.invalidateQueries({ queryKey: [name, ws] }),
        ),
      );
    },
  });
}

/** Begin server-authenticated Instagram authorization; navigation belongs to the screen. */
export function useConnectInstagram(ws: string) {
  return useMutation<
    { authorize_url: string },
    AppError,
    { purpose: "connect" | "reconnect"; social_account_id?: string }
  >({
    mutationFn: (body) => unwrap(
      api.POST("/api/v1/workspaces/{workspace_id}/social-accounts/instagram/connect", {
        params: { path: { workspace_id: ws } },
        body,
      }),
    ),
  });
}

/** The plain-language reason of an error code (what, then what to do), from the shared catalog. */
export function useErrorText() {
  const { t } = useTranslation();
  return (code: string | null | undefined) => {
    const what = code ? t(`errors.${code}.what`, { defaultValue: "" }) : "";
    const next = code ? t(`errors.${code}.next`, { defaultValue: "" }) : "";
    return { what, next };
  };
}

/** Local time in the workspace timezone (INV-19). */
export function useLocalTime() {
  const { i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  return (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: workspace.timezone,
    });
}

/** The workspace members and the pending invites (members screen). */
export function useMembers(ws: string) {
  return useQuery<Member[], AppError>({
    queryKey: membersKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/members", {
          params: { path: { workspace_id: ws } },
        }),
      ).then((page) => page.items),
    retry: false,
  });
}

export function usePendingInvites(ws: string) {
  return useQuery<PendingInvite[], AppError>({
    queryKey: invitesKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/invites", {
          params: { path: { workspace_id: ws } },
        }),
      ).then((page) => page.items),
    retry: false,
  });
}

/** Create an invite; the response carries the one-time link. */
export function useCreateInvite(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<Invite, AppError, Role>({
    mutationFn: (role) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/invites", {
          params: { path: { workspace_id: ws } },
          body: { role },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invites", ws] }),
  });
}

export function useRevokeInvite(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, string>({
    mutationFn: (inviteId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/invites/{invite_id}/revoke", {
          params: { path: { workspace_id: ws, invite_id: inviteId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invites", ws] }),
  });
}

export function useChangeMemberRole(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<Member, AppError, { userId: string; role: Role }>({
    mutationFn: ({ userId, role }) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: ws, user_id: userId } },
          body: { role },
        }),
      ),
    onSuccess: () =>
      Promise.all(MEMBER_QUERY_KEYS.map((name) => queryClient.invalidateQueries({ queryKey: [name, ws] }))),
  });
}

export function useRemoveMember(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, string>({
    mutationFn: (userId) =>
      unwrap(
        api.DELETE("/api/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: ws, user_id: userId } },
        }),
      ),
    onSuccess: () =>
      Promise.all(MEMBER_QUERY_KEYS.map((name) => queryClient.invalidateQueries({ queryKey: [name, ws] }))),
  });
}
