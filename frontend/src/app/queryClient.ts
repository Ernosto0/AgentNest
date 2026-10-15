import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { AppError } from "@/api/errors";
import { meKey } from "@/features/auth/hooks";

/**
 * One place that reacts to an expired session: any request answered with AUTH_REQUIRED
 * clears the cached user, which sends the auth guard to the login screen.
 */
export function createQueryClient(): QueryClient {
  const handleError = (error: unknown) => {
    if (error instanceof AppError && error.code === "AUTH_REQUIRED") {
      client.setQueryData(meKey, null);
    }
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: handleError }),
    mutationCache: new MutationCache({ onError: handleError }),
    defaultOptions: {
      queries: {
        retry: (count, error) => !(error instanceof AppError && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}
