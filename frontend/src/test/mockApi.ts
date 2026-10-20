import { vi } from "vitest";

export interface RecordedRequest {
  method: string;
  path: string;
  /** The query string, e.g. "?tab=drafts" ("" if none). */
  search: string;
  headers: Headers;
  body: unknown;
}

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

export const problem = (status: number, code: string, extra: Record<string, unknown> = {}) =>
  new Response(
    JSON.stringify({
      type: "about:blank",
      title: "Error",
      status,
      code,
      params: {},
      detail: "ignored: the UI renders its own text from the code",
      request_id: "req-123",
      ...extra,
    }),
    { status, headers: { "content-type": "application/problem+json" } },
  );

export const noContent = () => new Response(null, { status: 204 });

/** Requests every screen makes in the background; a test overrides them to assert on them. */
const BACKGROUND: [RegExp, () => Response][] = [
  [
    /^GET \/api\/v1\/workspaces\/[^/]+\/notifications$/,
    () => json({ items: [], unread_count: 0, next_cursor: null }),
  ],
];

/**
 * Replace the global `fetch` with a router keyed by "METHOD /path". Unmatched requests fail the
 * test loudly instead of silently hitting the network. Returns the recorded requests.
 */
export function mockApi(routes: Record<string, Handler>): RecordedRequest[] {
  const recorded: RecordedRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url, "http://localhost");
      const multipart = (input.headers.get("content-type") ?? "").startsWith("multipart/");
      // jsdom files cannot be streamed by Node's Request, so a multipart body is not read: tests spy on
      // FormData.append to see the file. Every other body is JSON.
      const text = multipart ? "" : await input.clone().text();
      const entry: RecordedRequest = {
        method: input.method,
        path: url.pathname,
        search: url.search,
        headers: input.headers,
        body: text ? JSON.parse(text) : undefined,
      };
      recorded.push(entry);
      const key = `${input.method} ${url.pathname}`;
      const handler = routes[key] ?? BACKGROUND.find(([pattern]) => pattern.test(key))?.[1];
      if (!handler) throw new Error(`unmocked request: ${key}`);
      return handler(entry);
    }),
  );
  return recorded;
}
