import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setCsrfToken, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { AuthSession, Me, Meta } from "@/api/types";
import type { Language } from "@/i18n";

export const meKey = ["me"] as const;
export const metaKey = ["meta"] as const;
export const sessionsKey = ["auth", "sessions"] as const;

/** The signed-in user, or `null` when there is no valid session (never throws for 401). */
async function fetchMe(): Promise<Me | null> {
  try {
    const me = await unwrap(api.GET("/api/v1/auth/me"));
    setCsrfToken(me.csrf_token); // required by every later state-changing request
    return me;
  } catch (error) {
    if (error instanceof AppError && error.code === "AUTH_REQUIRED") {
      setCsrfToken(null);
      return null;
    }
    throw error;
  }
}

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: fetchMe, retry: false, staleTime: 60_000 });
}

export function useMeta() {
  return useQuery<Meta>({
    queryKey: metaKey,
    queryFn: () => unwrap(api.GET("/api/v1/meta")),
    staleTime: Infinity,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, { email: string; password: string }>({
    mutationFn: (body) => unwrap<void>(api.POST("/api/v1/auth/login", { body })),
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: meKey });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, AppError>({
    mutationFn: () => unwrap<void>(api.POST("/api/v1/auth/logout")),
    onSettled: () => {
      setCsrfToken(null);
      queryClient.clear(); // nothing from this session may linger in memory
      queryClient.setQueryData(meKey, null);
    },
  });
}

/** Save the UI language on the account (PATCH /auth/me). */
export function useSaveLocale() {
  const queryClient = useQueryClient();
  return useMutation<Me, AppError, Language>({
    mutationFn: (ui_locale) => unwrap(api.PATCH("/api/v1/auth/me", { body: { ui_locale } })),
    onSuccess: (me) => queryClient.setQueryData(meKey, me),
  });
}

/** Save the display name on the account (PATCH /auth/me); the server trims and bounds it. */
export function useSaveDisplayName() {
  const queryClient = useQueryClient();
  return useMutation<Me, AppError, string>({
    mutationFn: (display_name) => unwrap(api.PATCH("/api/v1/auth/me", { body: { display_name } })),
    onSuccess: (me) => queryClient.setQueryData(meKey, me),
  });
}

export function useSessions() {
  return useQuery<AuthSession[]>({
    queryKey: sessionsKey,
    queryFn: () => unwrap(api.GET("/api/v1/auth/sessions")),
    staleTime: 30_000,
  });
}

export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, string>({
    mutationFn: (sessionId: string) =>
      unwrap<void>(
        api.DELETE("/api/v1/auth/sessions/{session_id}", {
          params: { path: { session_id: sessionId } },
        })
      ),
    // Refresh after any outcome: a 404 means that session already ended elsewhere.
    onSettled: () => queryClient.invalidateQueries({ queryKey: sessionsKey }),
  });
}

export function useRevokeAllSessions() {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, boolean | undefined>({
    mutationFn: (includeCurrent = false) =>
      unwrap<void>(
        api.POST("/api/v1/auth/sessions/revoke-all", {
          body: { include_current: includeCurrent },
        })
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: sessionsKey }),
  });
}

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation<void, AppError, { current_password: string; new_password: string }>({
    mutationFn: (body) => unwrap<void>(api.POST("/api/v1/auth/password", { body })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sessionsKey });
    },
  });
}

export function useRequestPasswordReset() {
  return useMutation<unknown, AppError, { email: string }>({
    mutationFn: (body) =>
      unwrap(api.POST("/api/v1/auth/password-reset/request", { body })),
  });
}

export function useConfirmPasswordReset() {
  return useMutation<void, AppError, { token: string; new_password: string }>({
    mutationFn: (body) =>
      unwrap<void>(api.POST("/api/v1/auth/password-reset/confirm", { body })),
  });
}
