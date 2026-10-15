import createClient from "openapi-fetch";
import i18n from "@/i18n";
import { AppError, parseProblem } from "./errors";
import type { paths } from "./schema";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// The CSRF token belongs to the current session and comes from GET /auth/me.
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/**
 * Typed API client: sends the session cookie, the CSRF header on state-changing requests and
 * the UI language. `fetch` is looked up at call time so tests can replace it.
 */
export function createApiClient(options: { fetch?: typeof fetch } = {}) {
  const client = createClient<paths>({
    baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
    credentials: "include",
    fetch: options.fetch ?? ((request) => globalThis.fetch(request)),
  });
  client.use({
    onRequest({ request }) {
      request.headers.set("Accept-Language", i18n.language);
      if (UNSAFE_METHODS.has(request.method) && csrfToken) {
        request.headers.set("X-CSRF-Token", csrfToken);
      }
      return request;
    },
  });
  return client;
}

export const api = createApiClient();

interface Result<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Resolve to the response data, or throw an `AppError` (problem+json or network failure). */
export async function unwrap<T>(request: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await request;
  } catch {
    throw new AppError("NETWORK_ERROR", 0);
  }
  if (!result.response.ok) {
    throw parseProblem(result.response.status, result.error);
  }
  return result.data as T; // 204 responses have no body
}
