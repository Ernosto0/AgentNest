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
import { useAgentOverviews, useAppointmentsVisible, useReadinessVisible, useYesterdayReport } from "./hooks";
import { InsightsPerformanceCard } from "./InsightsPerformanceCard";
import { ReadinessCard } from "./ReadinessCard";
import { TodayPulse } from "./TodayPulse";
import { UpcomingPanel, type CreateContent } from "./UpcomingPanel";

/**
 * Today (user-journeys §1, ui-spec §4.2). Reading order, top to bottom:
 * blocking notices → today's numbers → the assistant beside what waits for the owner →
 * the content plan beside appointments and readiness → Instagram performance.
 * On phones "what waits for you" moves to the very top; DOM order serves desktop and the
 * flex `order` utilities serve the single column (the "now" band uses `display: contents`).
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

  const showAppointments = useAppointmentsVisible();
  const showReadiness = useReadinessVisible();
  const railCount = Number(showAppointments) + Number(showReadiness);

  return (
    <div className="flex flex-col gap-5 lg:gap-6">
      <Banners accounts={activeAccounts} canReconnect={isOwner} />

      <div className="order-2 lg:order-none">
        <TodayPulse report={report.data} yesterday={yesterday.data} pending={report.isPending} failed={report.isError} />
      </div>

      <div className="contents lg:grid lg:grid-cols-12 lg:items-stretch lg:gap-6">
        <AssistantPanel
          className="order-3 lg:order-none lg:col-span-7"
          accounts={activeAccounts}
          overviews={overviews}
          canControl={isOwner}
          pending={accounts.isPending}
          error={accounts.error}
        />
        <AttentionPanel
          className="order-1 lg:order-none lg:col-span-5"
          metrics={metrics}
          pending={report.isPending || accounts.isPending}
          error={report.error ?? accounts.error}
          accounts={activeAccounts}
          overviews={overviews}
        />
      </div>

      <div className="order-4 grid items-start gap-5 lg:order-none xl:grid-cols-12 xl:gap-6">
        <UpcomingPanel onCreate={onCreate} className={railCount > 0 ? "xl:col-span-7" : "xl:col-span-12"} />
        {railCount > 0 ? (
          <div className={`grid content-start gap-5 xl:col-span-5 xl:grid-cols-1 xl:gap-6 ${railCount > 1 ? "md:grid-cols-2" : ""}`}>
            <AppointmentsCard />
            <ReadinessCard />
          </div>
        ) : null}
      </div>

      <div className="order-5 lg:order-none">
        <InsightsPerformanceCard workspaceId={workspace.id} accounts={activeAccounts} isOwner={isOwner} />
      </div>
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
          className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border border-danger/30 bg-danger-subtle px-4 py-3.5 sm:px-5"
        >
          <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-danger text-lg text-on-action">
            <CriticalIcon />
          </span>
          <p className="min-w-0 flex-1 basis-64 font-medium text-primary">{t("home.banner.needs_reauth")}</p>
          {canReconnect ? (
            <Link
              to={`/w/${workspace.id}/more/settings/connections`}
              className={`inline-flex min-h-11 items-center rounded-control bg-danger px-4 text-body font-semibold text-on-action hover:bg-danger-hover ${FOCUS}`}
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
          className="flex items-center gap-4 rounded-2xl border border-attention/30 bg-attention-subtle px-4 py-3.5 sm:px-5"
        >
          <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-attention text-lg text-on-action">
            <AlertIcon />
          </span>
          <span className="font-medium text-primary">{t("home.banner.degraded")}</span>
        </div>
      ) : null}
    </>
  );
}
