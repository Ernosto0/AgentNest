import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { PushConfig, PushDevice, PushPreferences } from "@/api/types";
import { useMe } from "@/features/auth/hooks";
import { subscribeThisDevice, unsubscribeThisDevice, type PushOutcome } from "./push";

export type PushCategory = keyof PushPreferences;

export const PUSH_CATEGORIES: readonly PushCategory[] = ["approvals", "questions", "failures"];

export const pushConfigKey = (ws: string) => ["push-config", ws] as const;
export const pushDevicesKey = (ws: string) => ["push-devices", ws] as const;
export const pushPreferencesKey = (ws: string) => ["push-preferences", ws] as const;

const path = (ws: string) => ({ workspace_id: ws });

/** Whether the server can send pushes at all (VAPID configured). Disabled: hide every push control. */
export function usePushConfig(ws: string, enabled = true) {
  return useQuery<PushConfig, AppError>({
    queryKey: pushConfigKey(ws),
    queryFn: () =>
      unwrap(api.GET("/api/v1/workspaces/{workspace_id}/push-subscriptions/config", { params: { path: path(ws) } })),
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function usePushDevices(ws: string, enabled = true) {
  return useQuery<PushDevice[], AppError>({
    queryKey: pushDevicesKey(ws),
    queryFn: async () =>
      (await unwrap(api.GET("/api/v1/workspaces/{workspace_id}/push-subscriptions", { params: { path: path(ws) } }))).items,
    enabled,
    retry: false,
  });
}

export function usePushPreferences(ws: string, enabled = true) {
  return useQuery<PushPreferences, AppError>({
    queryKey: pushPreferencesKey(ws),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/push-subscriptions/preferences", {
          params: { path: path(ws) },
        }),
      ),
    enabled,
    retry: false,
  });
}

export function useSavePushPreferences(ws: string) {
  const queryClient = useQueryClient();
  return useMutation<PushPreferences, AppError, Partial<PushPreferences>>({
    mutationFn: (body) =>
      unwrap(
        api.PUT("/api/v1/workspaces/{workspace_id}/push-subscriptions/preferences", {
          params: { path: path(ws) },
          body,
        }),
      ),
    onSuccess: (saved) => queryClient.setQueryData(pushPreferencesKey(ws), saved),
  });
}

/** Ask permission, subscribe this browser, register it, and switch approvals on if asked. */
export function useEnablePush(ws: string) {
  const queryClient = useQueryClient();
  const me = useMe();
  const save = useSavePushPreferences(ws);
  return useMutation<PushOutcome, AppError, { approvals?: boolean } | void>({
    mutationFn: async (options) => {
      const outcome = await subscribeThisDevice(ws, me.data?.user.id);
      if (outcome.status === "subscribed" && options?.approvals) {
        await save.mutateAsync({ approvals: true });
      }
      return outcome;
    },
    onSuccess: (outcome) => {
      if (outcome.status === "subscribed") {
        void queryClient.invalidateQueries({ queryKey: pushDevicesKey(ws) });
      }
    },
  });
}

export function useRemovePushDevice(ws: string) {
  const queryClient = useQueryClient();
  const me = useMe();
  return useMutation<void, AppError, string>({
    mutationFn: (deviceId) => unsubscribeThisDevice(ws, deviceId, me.data?.user.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: pushDevicesKey(ws) }),
  });
}
