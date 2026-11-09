import { useQueries, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AppError } from "@/api/errors";
import type { components } from "@/api/schema";
import type {
  ActivityEntry,
  CalendarAppointment,
  CalendarConnection,
  ContentItem,
  DailyReport,
  SocialAccount,
} from "@/api/types";
import { useReadiness } from "@/features/knowledge/hooks";
import { shiftDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";

export type AgentOverview = components["schemas"]["AgentOverview"];
export type InsightsSummary = components["schemas"]["InsightsSummaryOut"];
export type InsightsContentList = components["schemas"]["InsightsContentListOut"];
export type AudienceData = components["schemas"]["AudienceOut"];

const HOME_LIST = 3;
/** Scheduled items fetched for the week view; a full page means there may be more. */
export const SCHEDULED_WEEK_LIMIT = 50;

/** The most recent posts that failed for good, newest first. */
export function useRecentFailures(ws: string) {
  return useQuery<ContentItem[], AppError>({
    queryKey: ["content-items", ws, "home-failed"],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/content-items", {
            params: { path: { workspace_id: ws }, query: { status: "failed", limit: HOME_LIST } },
          }),
        )
      ).items,
    refetchInterval: 60_000,
  });
}

/** Shared overview queries for all connected accounts (refreshed every 15s). */
export function useAgentOverviews(ws: string, accounts: SocialAccount[]) {
  const activeAccounts = accounts.filter((a) => a.status !== "disconnected");
  return useQueries({
    queries: activeAccounts.map((a) => ({
      queryKey: ["agent", ws, a.id, "overview"],
      queryFn: () =>
        unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent", {
            params: { path: { workspace_id: ws, account_id: a.id } },
          }),
        ),
      retry: false,
      refetchInterval: 15_000,
    })),
  });
}

export interface ScheduledDay {
  dayStr: string; // YYYY-MM-DD
  stories: ContentItem[];
  posts: ContentItem[];
  total: number;
  hasStoryGap: boolean;
  isToday: boolean;
  isTomorrow: boolean;
}

/** Scheduled content for the upcoming 7 days, grouped by local date in workspace timezone. */
export function useScheduledWeek(ws: string, timezone: string) {
  const query = useQuery<ContentItem[], AppError>({
    queryKey: ["content-items", ws, "home-scheduled-week"],
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/workspaces/{workspace_id}/content-items", {
            params: { path: { workspace_id: ws }, query: { tab: "scheduled", limit: SCHEDULED_WEEK_LIMIT } },
          }),
        )
      ).items,
    refetchInterval: 60_000,
  });

  const today = todayIn(timezone);
  const tomorrow = shiftDay(today, 1);

  const days: ScheduledDay[] = [];
  const items = query.data ?? [];

  // 7 days starting from today
  for (let i = 0; i < 7; i++) {
    const dayStr = shiftDay(today, i);
    const dayItems = items.filter((item) => {
      if (!item.scheduled_at) return false;
      const itemDay = todayIn(timezone, new Date(item.scheduled_at));
      return itemDay === dayStr;
    });

    const stories = dayItems.filter((item) => item.content_type === "story_image");
    const posts = dayItems.filter((item) => item.content_type === "feed_image");

    days.push({
      dayStr,
      stories,
      posts,
      total: dayItems.length,
      hasStoryGap: stories.length === 0,
      isToday: dayStr === today,
      isTomorrow: dayStr === tomorrow,
    });
  }

  const allStories = items.filter((item) => item.content_type === "story_image");
  const allPosts = items.filter((item) => item.content_type === "feed_image");

  return {
    ...query,
    items,
    days,
    stories: allStories,
    posts: allPosts,
  };
}

/** Agent audit activity feed (agent actions only, newest first, at most 8 entries). */
export function useRecentAgentActivity(ws: string, enabled = true) {
  return useQuery<ActivityEntry[], AppError>({
    queryKey: ["activity", ws, "home-agent"],
    enabled,
    queryFn: async () => {
      const page = await unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/activity", {
          params: { path: { workspace_id: ws }, query: { limit: 20 } },
        }),
      );
      // Filter to agent actions only (per decision)
      return page.items.filter((entry) => entry.actor.type === "agent").slice(0, 8);
    },
    refetchInterval: 30_000,
  });
}

/** Calendar connections & upcoming appointments for today and tomorrow. */
export function useAppointmentsInfo(ws: string, timezone: string) {
  const connectionsQuery = useQuery<CalendarConnection[], AppError>({
    queryKey: ["calendar-connections", ws],
    queryFn: async () => (await unwrap(api.GET("/api/v1/workspaces/{workspace_id}/calendar", { params: { path: { workspace_id: ws } } }))).items,
    refetchInterval: 60_000,
  });

  const appointmentsQuery = useQuery<CalendarAppointment[], AppError>({
    queryKey: ["calendar-appointments", ws, "home"],
    queryFn: async () => (await unwrap(api.GET("/api/v1/workspaces/{workspace_id}/calendar/appointments", { params: { path: { workspace_id: ws } } }))).items,
    refetchInterval: 60_000,
  });

  const today = todayIn(timezone);
  const tomorrow = shiftDay(today, 1);

  const activeConnections = (connectionsQuery.data ?? []).filter((c) => !c.disconnected_at);
  const hasConnectedCalendar = activeConnections.length > 0;

  const relevantAppointments = (appointmentsQuery.data ?? []).filter((appt) => {
    if (appt.status === "cancelled") return false;
    const apptDay = todayIn(timezone, new Date(appt.start_at));
    return apptDay === today || apptDay === tomorrow;
  });

  return {
    connections: connectionsQuery,
    appointments: appointmentsQuery,
    hasConnectedCalendar,
    activeAppointments: relevantAppointments,
    isPending: connectionsQuery.isPending || appointmentsQuery.isPending,
    error: connectionsQuery.error ?? appointmentsQuery.error,
  };
}

/** Yesterday's daily report for trend comparisons. */
export function useYesterdayReport(ws: string, timezone: string) {
  const today = todayIn(timezone);
  const yesterday = shiftDay(today, -1);
  return useQuery<DailyReport, AppError>({
    queryKey: ["report", ws, yesterday, "home-yesterday"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/reports/daily", {
          params: { path: { workspace_id: ws }, query: { date: yesterday } },
        }),
      ),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** Authoritative counts; missing/failed data must never become zero. */
export function useHomeAttention(ws: string) {
  return useQuery<components["schemas"]["HomeAttentionOut"], AppError>({
    queryKey: ["content-items", ws, "home-attention"],
    queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/home/attention", {
      params: { path: { workspace_id: ws } },
    })),
    refetchInterval: 30_000,
    retry: false,
  });
}

/** Account insights performance summary (7d or 28d). */
export function useInsightsSummary(ws: string, accountId: string | undefined, range: "7d" | "28d" = "7d") {
  return useQuery<InsightsSummary, AppError>({
    queryKey: ["insights", ws, accountId, "summary", range],
    queryFn: async () => {
      if (!accountId) throw new Error("No account ID");
      return unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/insights/summary", {
          params: { path: { workspace_id: ws, account_id: accountId }, query: { range } },
        }),
      );
    },
    enabled: Boolean(accountId),
    refetchInterval: 5 * 60_000,
  });
}

/** Recent content media performance. */
export function useInsightsContent(
  ws: string,
  accountId: string | undefined,
  kind?: "story" | "feed",
  limit = 10,
) {
  return useQuery<InsightsContentList, AppError>({
    queryKey: ["insights", ws, accountId, "content", kind, limit],
    queryFn: async () => {
      if (!accountId) throw new Error("No account ID");
      return unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/insights/content", {
          params: { path: { workspace_id: ws, account_id: accountId }, query: { kind, limit } },
        }),
      );
    },
    enabled: Boolean(accountId),
    refetchInterval: 5 * 60_000,
  });
}

/** Audience demographics and online hours. */
export function useInsightsAudience(ws: string, accountId: string | undefined) {
  return useQuery<AudienceData, AppError>({
    queryKey: ["insights", ws, accountId, "audience"],
    queryFn: async () => {
      if (!accountId) throw new Error("No account ID");
      return unwrap(
        api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/insights/audience", {
          params: { path: { workspace_id: ws, account_id: accountId } },
        }),
      );
    },
    enabled: Boolean(accountId),
    refetchInterval: 15 * 60_000,
  });
}

/**
 * Readiness as the layout needs it: "open" while requirements remain (the card shows),
 * "ready" once complete (the card disappears), otherwise still loading or failed.
 */
export function useReadinessState(): "pending" | "open" | "ready" | "error" {
  const { workspace } = useCurrentWorkspace();
  const readiness = useReadiness(workspace.id);
  if (readiness.isError) return "error";
  if (!readiness.data) return "pending";
  return readiness.data.level === "ready" ? "ready" : "open";
}
