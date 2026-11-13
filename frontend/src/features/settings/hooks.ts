import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { CalendarAppointment, CalendarConnection, ChannelLink, ChannelLinkCode, Invite, Member, PendingInvite, Role, SocialAccount, SystemHealth } from "@/api/types";
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
  return useMutation<Invite, AppError, Role | { role: Role; email?: string }>({
    mutationFn: (param) => {
      const body = typeof param === "string" ? { role: param } : { role: param.role, email: param.email };
      return unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/invites", {
          params: { path: { workspace_id: ws } },
          body,
        }),
      );
    },
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

export interface WorkspaceDeletionStatus {
  workspace_id: string;
  status: string;
  is_deleting: boolean;
  deletion_requested_at: string | null;
  deletion_scheduled_at: string | null;
  days_remaining: number | null;
  can_cancel: boolean;
}

export function useWorkspaceDeletionStatus(ws: string) {
  return useQuery<WorkspaceDeletionStatus, AppError>({
    queryKey: ["workspace-deletion-status", ws],
    queryFn: async () =>
      (await unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/deletion-status", {
          params: { path: { workspace_id: ws } },
        }),
      )) as unknown as WorkspaceDeletionStatus,
  });
}

export function useRequestWorkspaceDeletion(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkspaceDeletionStatus, AppError>({
    mutationFn: async () =>
      (await unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/delete-request", {
          params: { path: { workspace_id: ws } },
        }),
      )) as unknown as WorkspaceDeletionStatus,
    onSuccess: (status) => {
      queryClient.setQueryData(["workspace-deletion-status", ws], status);
      // The request flips the workspace status, pauses automation and disconnects accounts.
      return Promise.all(
        ["workspace", "social-accounts", "automation", "agent", "readiness"].map((name) =>
          queryClient.invalidateQueries({ queryKey: [name, ws] }),
        ),
      );
    },
  });
}

export function useCancelWorkspaceDeletion(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkspaceDeletionStatus, AppError>({
    mutationFn: async () =>
      (await unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/cancel-deletion", {
          params: { path: { workspace_id: ws } },
        }),
      )) as unknown as WorkspaceDeletionStatus,
    onSuccess: (status) => {
      queryClient.setQueryData(["workspace-deletion-status", ws], status);
      return queryClient.invalidateQueries({ queryKey: ["workspace", ws] });
    },
  });
}

// --- Owner messaging channels (Phase 9, ADR-012, Session 02) ---

export const channelLinksKey = (ws: string) => ["channel-links", ws] as const;

export function useChannelLinks(ws: string) {
  return useQuery<ChannelLink[], AppError>({
    queryKey: channelLinksKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/channels/links", {
          params: { path: { workspace_id: ws } },
        }),
      ),
    retry: false,
  });
}

export function useGenerateChannelLinkCode(ws: string) {
  return useMutation<ChannelLinkCode, AppError, { channel?: "telegram" } | void>({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/channels/link-code", {
          params: { path: { workspace_id: ws } },
          body: { channel: body?.channel ?? "telegram" },
        }),
      ),
  });
}

export function useUnlinkChannel(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, string>({
    mutationFn: async (linkId) => {
      const response = await api.DELETE(
        "/api/v1/workspaces/{workspace_id}/channels/links/{link_id}",
        {
          params: { path: { workspace_id: ws, link_id: linkId } },
        },
      );
      if (response.error) {
        throw response.error;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelLinksKey(ws) });
    },
  });
}

// --- Google Calendar & appointments integration ---

export const calendarConnectionsKey = (ws: string) => ["calendar-connections", ws] as const;
export const calendarAppointmentsKey = (ws: string) => ["calendar-appointments", ws] as const;

export function useCalendarConnections(ws: string) {
  return useQuery<CalendarConnection[], AppError>({
    queryKey: calendarConnectionsKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/calendar", {
          params: { path: { workspace_id: ws } },
        }),
      ).then((page) => page.items),
    retry: false,
  });
}

export function useCalendarAppointments(ws: string) {
  return useQuery<CalendarAppointment[], AppError>({
    queryKey: calendarAppointmentsKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/calendar/appointments", {
          params: { path: { workspace_id: ws } },
        }),
      ).then((page) => page.items),
    retry: false,
  });
}

export function useConnectGoogleCalendar(ws: string) {
  return useMutation<{ authorize_url: string }, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/calendar/connect/google", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useReconnectGoogleCalendar(ws: string) {
  return useMutation<{ authorize_url: string }, AppError, string>({
    mutationFn: (connectionId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/calendar/{connection_id}/reconnect/google", {
          params: { path: { workspace_id: ws, connection_id: connectionId } },
        }),
      ),
  });
}

export function useConnectMockCalendar(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CalendarConnection,
    AppError,
    { account_email?: string; calendar_summary?: string; default_slot_duration_minutes?: number } | void
  >({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/calendar/connect-mock", {
          params: { path: { workspace_id: ws } },
          body: {
            account_email: body?.account_email ?? null,
            calendar_summary: body?.calendar_summary ?? null,
            default_slot_duration_minutes: body?.default_slot_duration_minutes ?? 30,
          },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: calendarConnectionsKey(ws) }),
        queryClient.invalidateQueries({ queryKey: ["agent", ws] }),
        queryClient.invalidateQueries({ queryKey: ["activity", ws] }),
      ]),
  });
}

export function useUpdateCalendarConnection(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CalendarConnection,
    AppError,
    { connectionId: string; default_slot_duration_minutes: number }
  >({
    mutationFn: ({ connectionId, default_slot_duration_minutes }) =>
      unwrap(
        api.PATCH("/api/v1/workspaces/{workspace_id}/calendar/{connection_id}", {
          params: { path: { workspace_id: ws, connection_id: connectionId } },
          body: { default_slot_duration_minutes },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: calendarConnectionsKey(ws) }),
  });
}

export function useDisconnectCalendar(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<CalendarConnection, AppError, string>({
    mutationFn: (connectionId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/calendar/{connection_id}/disconnect", {
          params: { path: { workspace_id: ws, connection_id: connectionId } },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: calendarConnectionsKey(ws) }),
        queryClient.invalidateQueries({ queryKey: ["agent", ws] }),
        queryClient.invalidateQueries({ queryKey: ["activity", ws] }),
      ]),
  });
}
