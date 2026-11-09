import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReportMetric, SocialAccount } from "@/api/types";
import { AlertIcon, CriticalIcon } from "@/components/icons";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useDailyReport } from "@/features/reports/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AppointmentsCard } from "./AppointmentsCard";
import { AssistantPanel } from "./AssistantPanel";
import { AttentionPanel } from "./AttentionPanel";
import { FOCUS } from "./DashboardPanel";
import { useAgentOverviews, useReadinessState, useYesterdayReport } from "./hooks";
import { InsightsPerformanceCard } from "./InsightsPerformanceCard";
import { ReadinessCard } from "./ReadinessCard";
import { TodayPulse } from "./TodayPulse";
import { UpcomingPanel, type CreateContent } from "./UpcomingPanel";

/**
 * Today (user-journeys §1, ui-spec §4.2).
 *
 * Desktop: notices and today's numbers span the page; below them two independent columns keep
 * their natural heights (no card is stretched to match its neighbour). The main column holds the
 * assistant and the content plan; the side column holds what waits for the owner, appointments,
 * readiness and, while readiness is complete, Instagram performance. Open readiness requirements
 * are tall, so performance then moves to a full-width band below to keep the columns balanced.
 *
 * Phones: one column ordered by urgency. The column wrappers use `display: contents` below `lg`,
 * so the flex `order` utilities can interleave their children.
 */
export function Dashboard({ onCreate }: { onCreate: CreateContent }) {
  const { workspace, role } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const activeAccounts = accounts.data ?? [];
  const report = useDailyReport(workspace.id, null);
  const yesterday = useYesterdayReport(workspace.id, workspace.timezone);
  const metrics = new Map<string, ReportMetric>((report.data?.metrics ?? []).map((m) => [m.key, m]));
  const overviews = useAgentOverviews(workspace.id, activeAccounts);
  const isOwner = role === "owner";
  const readiness = useReadinessState();
  const insightsBeside = readiness === "ready" || readiness === "pending";

  const insights = <InsightsPerformanceCard workspaceId={workspace.id} accounts={activeAccounts} isOwner={isOwner} />;

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Banners accounts={activeAccounts} canReconnect={isOwner} />

      <div className="order-2 lg:order-none">
        <TodayPulse report={report.data} yesterday={yesterday.data} pending={report.isPending} failed={report.isError} />
      </div>

      <div className="contents lg:grid lg:grid-cols-12 lg:items-start lg:gap-5">
        <div className="contents lg:col-span-7 lg:flex lg:flex-col lg:gap-5">
          <AssistantPanel
            className="order-3 lg:order-none"
            accounts={activeAccounts}
            overviews={overviews}
            canControl={isOwner}
            pending={accounts.isPending}
            error={accounts.error}
          />
          <UpcomingPanel onCreate={onCreate} className="order-4 lg:order-none" />
        </div>

        <div className="contents lg:col-span-5 lg:flex lg:flex-col lg:gap-5">
          <AttentionPanel
            className="order-1 lg:order-none"
            metrics={metrics}
            pending={report.isPending || accounts.isPending}
            error={report.error ?? accounts.error}
            accounts={activeAccounts}
            overviews={overviews}
          />
          <div className="order-5 empty:hidden lg:order-none">
            <AppointmentsCard />
          </div>
          <div className="order-6 empty:hidden lg:order-none">
            <ReadinessCard />
          </div>
          {insightsBeside ? <div className="order-7 lg:order-none">{insights}</div> : null}
        </div>
      </div>

      {insightsBeside ? null : <div className="order-7 lg:order-none">{insights}</div>}
    </div>
  );
}

/** Account-blocking notices come first and span the page (ui-spec §4.2). */
function Banners({ accounts, canReconnect }: { accounts: SocialAccount[]; canReconnect: boolean }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const reauth = accounts.some((a) => a.status === "needs_reauth");
  const degraded = accounts.some((a) => a.status === "degraded");
  return (
    <>
      {reauth ? (
        <div
          role="alert"
          data-testid="banner-needs-reauth"
          className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border border-danger/30 bg-danger-subtle px-4 py-3 sm:px-5"
        >
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-danger text-base text-on-action">
            <CriticalIcon />
          </span>
          <p className="min-w-0 flex-1 basis-64 font-medium text-primary">{t("home.banner.needs_reauth")}</p>
          {canReconnect ? (
            <Link
              to={`/w/${workspace.id}/more/settings/connections`}
              className={`inline-flex min-h-10 items-center rounded-control bg-danger px-4 text-body font-semibold text-on-action hover:bg-danger-hover ${FOCUS}`}
            >
              {t("home.banner.reconnect")}
            </Link>
          ) : (
            <p className="text-metadata text-secondary">{t("automation.ownerOnly")}</p>
          )}
        </div>
      ) : null}
      {degraded ? (
        <div
          role="status"
          data-testid="banner-degraded"
          className="flex items-center gap-4 rounded-2xl border border-attention/30 bg-attention-subtle px-4 py-3 sm:px-5"
        >
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-attention text-base text-on-action">
            <AlertIcon />
          </span>
          <span className="font-medium text-primary">{t("home.banner.degraded")}</span>
        </div>
      ) : null}
    </>
  );
}
