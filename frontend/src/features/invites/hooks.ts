import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { InviteAcceptOut } from "@/api/types";
import { meKey } from "@/features/auth/hooks";

export interface AcceptBody {
  token: string;
  email?: string;
  display_name?: string;
  password?: string;
}

/** Accept an invite (signed in, or as a new account). Refreshes the membership list on success. */
export function useAcceptInvite() {
  const queryClient = useQueryClient();
  return useMutation<InviteAcceptOut, AppError, AcceptBody>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/invites/accept", { body })),
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: meKey });
    },
  });
}
