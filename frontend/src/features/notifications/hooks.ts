import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { NotificationList } from "@/api/types";
import { notificationsKey } from "@/features/commands/hooks";

/** The caller's own notifications, newest first; `unreadOnly` asks the server for the unread ones. */
export function useNotifications(workspaceId: string, unreadOnly = false) {
  return useQuery<NotificationList, AppError>({
    queryKey: [...notificationsKey(workspaceId), unreadOnly ? "unread" : "all"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/notifications", {
          params: {
            path: { workspace_id: workspaceId },
            query: unreadOnly ? { limit: 30, unread: true } : { limit: 30 },
          },
        }),
      ),
    refetchInterval: 30_000,
  });
}

export function useMarkRead(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<unknown, AppError, string>({
    mutationFn: (notificationId) =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/notifications/{notification_id}/read", {
          params: { path: { workspace_id: workspaceId, notification_id: notificationId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationsKey(workspaceId) }),
  });
}

export function useMarkAllRead(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation<unknown, AppError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workspaces/{workspace_id}/notifications/read-all", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationsKey(workspaceId) }),
  });
}
