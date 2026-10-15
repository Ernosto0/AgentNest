import { vi } from "vitest";

export interface RecordedRequest {
  method: string;
  path: string;
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
      const text = await input.clone().text();
      const entry: RecordedRequest = {
        method: input.method,
        path: url.pathname,
        headers: input.headers,
        body: text ? JSON.parse(text) : undefined,
      };
      recorded.push(entry);
      const handler = routes[`${input.method} ${url.pathname}`];
      if (!handler) throw new Error(`unmocked request: ${input.method} ${url.pathname}`);
      return handler(entry);
    }),
  );
  return recorded;
}
