import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setCsrfToken, unwrap } from "@/api/client";
import { AppError } from "@/api/errors";
import type { Me, Meta } from "@/api/types";
import type { Language } from "@/i18n";

export const meKey = ["me"] as const;
export const metaKey = ["meta"] as const;

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
