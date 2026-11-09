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
  [/^GET \/api\/v1\/workspaces\/[^/]+\/home\/attention$/, () => json({ drafts: 0, unanswered_comments: 0 })],
  // Home reads these background feeds; a test that cares about them overrides the route.
  [/^GET \/api\/v1\/workspaces\/[^/]+\/social-accounts$/, () => json({ items: [], next_cursor: null })],
  [/^GET \/api\/v1\/workspaces\/[^/]+\/content-items$/, () => json({ items: [], next_cursor: null })],
  [/^GET \/api\/v1\/workspaces\/[^/]+\/activity$/, () => json({ items: [], next_cursor: null })],
  [/^GET \/api\/v1\/workspaces\/[^/]+\/calendar$/, () => json({ items: [] })],
  [/^GET \/api\/v1\/workspaces\/[^/]+\/calendar\/appointments$/, () => json({ items: [] })],
  [/^GET \/api\/v1\/workspaces\/[^/]+\/accounts\/[^/]+\/comments$/, () => json({ items: [], next_cursor: null })],
  [
    /^GET \/api\/v1\/workspaces\/[^/]+\/accounts\/[^/]+\/insights\/summary$/,
    () =>
      json({
        account_id: "00000000-0000-0000-0000-000000000001",
        range: "7d",
        status: "ok",
        updated_at: "2026-11-10T12:00:00Z",
        reach: 1200,
        reach_delta_pct: 15,
        views: 2400,
        views_delta_pct: 22,
        interactions: 180,
        interactions_delta_pct: 8,
        follower_count: 1420,
        follower_delta: 14,
        sparkline: [
          { date: "2026-11-04", reach: 140, views: 280 },
          { date: "2026-11-05", reach: 180, views: 320 },
          { date: "2026-11-06", reach: 160, views: 310 },
          { date: "2026-11-07", reach: 210, views: 400 },
          { date: "2026-11-08", reach: 190, views: 380 },
          { date: "2026-11-09", reach: 150, views: 330 },
          { date: "2026-11-10", reach: 170, views: 380 },
        ],
        is_simulated: true,
      }),
  ],
  [
    /^GET \/api\/v1\/workspaces\/[^/]+\/accounts\/[^/]+\/insights\/content$/,
    () => json({ items: [] }),
  ],
  [
    /^GET \/api\/v1\/workspaces\/[^/]+\/accounts\/[^/]+\/insights\/audience$/,
    () =>
      json({
        status: "ok",
        follower_count: 1420,
        online_hours: null,
        best_posting_window: null,
        demographics: null,
      }),
  ],
  [
    /^GET \/api\/v1\/workspaces\/[^/]+\/reports\/daily$/,
    () =>
      json({
        local_date: "2026-10-15",
        timezone: "Europe/Istanbul",
        period_start: "2026-10-14T21:00:00Z",
        period_end: "2026-10-15T09:00:00Z",
        generated_at: "2026-10-15T09:00:00Z",
        is_partial: true,
        definitions_version: "1",
        has_simulated_data: false,
        metrics: [],
        summary: { empty: true, text: "", sections: [] },
      }),
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
