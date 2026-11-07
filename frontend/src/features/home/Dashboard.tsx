import { useQueries } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import { CommandBar } from "@/features/commands/CommandBar";
import { ReadinessCard } from "./ReadinessCard";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReportMetric, SocialAccount } from "@/api/types";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, CriticalIcon, ImageIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMediaPreview } from "@/features/content/hooks";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { formatValue } from "@/features/reports/format";
import { useDailyReport } from "@/features/reports/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useRecentFailures, useUpcomingPosts } from "./hooks";

const LINK =
  "inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus transition-colors";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-4 bg-surface p-5" aria-labelledby={id} data-testid={id}>
      <h2 id={id} className="type-section text-primary">
        {title}
      </h2>
      {children}
    </Card>
  );
}

/** Home (user-journeys §1, J6): what is wrong, what waits for the owner, what is next, today's numbers. */
export function Dashboard() {
  const { workspace, role } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const report = useDailyReport(workspace.id, null);
  const metrics = new Map<string, ReportMetric>((report.data?.metrics ?? []).map((m) => [m.key, m]));
  return (
    <div className="flex flex-col gap-5">
      <Banners accounts={accounts.data ?? []} canReconnect={role === "owner"} />
      <Attention metrics={metrics} pending={report.isPending || accounts.isPending} error={report.error ?? accounts.error} accounts={accounts.data ?? []} />
      <CommandBar />
      <Upcoming />
      <ReadinessCard />
      <Numbers report={report.data} metrics={metrics} />
    </div>
  );
}

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
          className="flex flex-col gap-2 rounded-panel border border-danger/40 bg-danger-subtle p-4 text-primary"
        >
          <p className="flex items-start gap-2 font-medium text-danger">
            <CriticalIcon className="mt-0.5 shrink-0 text-xl text-danger" />
            <span className="text-primary">{t("home.banner.needs_reauth")}</span>
          </p>
          {canReconnect ? (
            <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK}>
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
          className="flex items-start gap-2 rounded-panel border border-attention/40 bg-attention-subtle p-4 font-medium text-primary"
        >
          <AlertIcon className="mt-0.5 shrink-0 text-xl text-attention" />
          <span>{t("home.banner.degraded")}</span>
        </div>
      ) : null}
    </>
  );
}

function Attention({ metrics, pending, error, accounts }: {
  metrics: Map<string, ReportMetric>; pending: boolean; error: Error | null; accounts: SocialAccount[];
}) {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const base = `/w/${workspace.id}`;
  const failures = useRecentFailures(workspace.id);
  const overviews = useQueries({ queries: accounts.filter(a => a.status !== "disconnected").map(a => ({
    queryKey: ["agent", workspace.id, a.id, "overview"],
    queryFn: () => unwrap(api.GET("/api/v1/workspaces/{workspace_id}/accounts/{account_id}/agent", { params: { path: { workspace_id: workspace.id, account_id: a.id } } })),
    retry: false, refetchInterval: 5000,
  })) });
  const questionsKnown = overviews.every(q => q.isSuccess);
  const questionCount = questionsKnown ? overviews.reduce((sum, q) => sum + (q.data?.pending_questions ?? 0), 0) : null;
  const rows = [
    { key: "pending_approvals_now", label: t("home.attention.approvals"), verb: t("core.reviewReply"), to: `${base}/approvals` },
    { key: "questions", label: t("core.questions"), verb: t("core.answerQuestion"), to: `${base}/more/agent/questions` },
    { key: "attention_now", label: t("home.attention.needsHuman"), verb: t("core.reviewReply"), to: `${base}/inbox?attention=needs_human` },
    { key: "content_on_hold_now", label: t("home.attention.onHold"), verb: t("core.reviewContent"), to: `${base}/content?tab=problems` },
  ].filter(row => row.key === "questions" || metrics.has(row.key)).map(row => ({ ...row, count: row.key === "questions" ? questionCount : metrics.get(row.key)?.value ?? null }));
  const hasFailure = (failures.data?.length ?? 0) > 0;
  const nothing = metrics.has("attention_now") && (role === "staff" || ["pending_approvals_now", "content_on_hold_now"].every(key => metrics.has(key))) && !pending && !error && questionsKnown && failures.isSuccess && !hasFailure && rows.every(row => row.count === 0);
  return <Section id="home-attention" title={t("home.attention.title")}>
    {error ? <ErrorMessage error={error} /> : null}
    {pending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
    {nothing ? <p data-testid="attention-none" className="flex items-center gap-3 py-3 text-success"><CheckIcon />{t("home.attention.none")}</p> : null}
    <ul className="divide-y divide-border">
      {accounts.filter(a => a.status === "needs_reauth").map(a => <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><span>@{a.username} · {t("home.banner.needs_reauth")}</span>{role === "owner" ? <Link className={LINK} to={`${base}/more/settings/connections`}>{t("home.banner.reconnect")}</Link> : <span>{t("automation.ownerOnly")}</span>}</li>)}
      {failures.data?.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><span className="flex flex-wrap items-center gap-2 text-danger">{item.title}{item.is_simulated ? <SimulatedBadge /> : null}</span><Link className={LINK} to={`${base}/content/${item.id}`}>{t("core.fixPost")}</Link></li>)}
      {rows.filter(row => row.count !== 0).map(row => <li key={row.key} data-testid={`attention-${row.key}`} className="flex flex-wrap items-center justify-between gap-3 py-3"><span className="flex items-center gap-3 font-medium">{row.label}<span className="rounded-control bg-attention-subtle px-2.5 py-1 text-attention">{row.count ?? t("core.unavailable")}</span></span><Link to={row.to} className={LINK}>{row.verb}</Link></li>)}
    </ul>
    {hasFailure ? <p className="text-metadata text-secondary">{t("core.previewList")}</p> : null}
    {failures.error ? <ErrorMessage error={failures.error} /> : null}
    {overviews.some(q => q.isError) ? <p role="status" className="text-secondary">{t("core.questions")}: {t("core.unavailable")}</p> : null}
  </Section>;
}

function UpcomingThumbnail({
  workspaceId,
  mediaId,
  deleted,
}: {
  workspaceId: string;
  mediaId: string | null;
  deleted?: boolean;
}) {
  const preview = useMediaPreview(workspaceId, deleted ? null : mediaId);
  if (!mediaId || deleted) {
    return (
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-surface-subtle text-secondary border border-border"
        aria-hidden="true"
      >
        <ImageIcon className="text-lg" />
      </div>
    );
  }
  if (preview.url) {
    return (
      <img
        src={preview.url}
        alt=""
        className="h-10 w-10 shrink-0 rounded-control object-cover border border-border"
      />
    );
  }
  return (
    <div
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-surface-subtle text-secondary border border-border"
      aria-hidden="true"
    >
      <ImageIcon className="text-lg" />
    </div>
  );
}

function Upcoming() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const upcoming = useUpcomingPosts(workspace.id);
  return (
    <Section id="home-upcoming" title={t("home.upcoming.title")}>
      {upcoming.isError ? <ErrorMessage error={upcoming.error} /> : null}
      {upcoming.isPending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
      {upcoming.data && upcoming.data.length === 0 ? (
        <div data-testid="upcoming-empty" className="flex flex-col gap-1">
          <p className="font-medium text-primary">{t("home.upcoming.empty")}</p>
          <p className="text-body text-secondary">{t("home.upcoming.emptyHint")}</p>
        </div>
      ) : null}
      {upcoming.data && upcoming.data.length > 0 ? (
        <><p className="text-metadata text-secondary">{t("core.previewOnly")}</p><ul className="divide-y divide-border">
          {upcoming.data.slice(0, 3).map((item) => (
            <li
              key={item.id}
              className="group flex items-center justify-between gap-3 py-3.5"
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <UpcomingThumbnail workspaceId={workspace.id} mediaId={item.media_asset_id} deleted={item.media_deleted} />
                <div className="flex flex-col min-w-0 gap-0.5">
                  <Link
                    to={`/w/${workspace.id}/content/${item.id}`}
                    className="font-semibold text-primary truncate hover:text-action transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  >
                    {item.title}
                  </Link>
                  <span className="flex flex-wrap items-center gap-2 text-metadata text-secondary">
                    {item.scheduled_at
                      ? new Date(item.scheduled_at).toLocaleString(i18n.language, {
                          dateStyle: "short",
                          timeStyle: "short",
                          timeZone: workspace.timezone,
                        })
                      : null}
                    {item.is_simulated ? <SimulatedBadge /> : null}
                  </span>
                </div>
              </div>
            </li>
          ))}
        </ul></>
      ) : null}
      <div>
        <Link to={`/w/${workspace.id}/content?tab=scheduled`} className={LINK}>
          {t("home.upcoming.all")}
        </Link>
      </div>
    </Section>
  );
}

const NUMBER_KEYS = ["inbound_messages", "replies_sent", "content_published", "integration_errors"] as const;

function Numbers({
  report,
  metrics,
}: {
  report: ReturnType<typeof useDailyReport>["data"];
  metrics: Map<string, ReportMetric>;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const shown = NUMBER_KEYS.map((key) => metrics.get(key)).filter(
    (metric): metric is ReportMetric => metric !== undefined,
  );
  const quiet = report !== undefined && report.summary.empty;
  const asOf = report
    ? new Date(report.period_end).toLocaleTimeString(i18n.language, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: workspace.timezone,
      })
    : "";
  return (
    <Section id="home-numbers" title={t("home.numbers.title")}>
      {report ? (
        <div className="flex flex-wrap items-center gap-2 text-metadata text-secondary">
          {report.is_partial ? <span>{t("home.numbers.asOf", { time: asOf })}</span> : null}
          {report.has_simulated_data ? <SimulatedBadge /> : null}
        </div>
      ) : null}
      {report && quiet ? (
        <p data-testid="numbers-empty" className="text-body text-secondary">
          {t("home.numbers.empty")}
        </p>
      ) : null}
      {report && !quiet ? (
        <dl className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
          {shown.map((metric) => {
            const label = t(`reports.metrics.${metric.key}`);
            const value = metric.value === null ? t("core.unavailable") : formatValue(metric.value, i18n.language);
            return (
              <div
                key={metric.key}
                data-testid={`number-${metric.key}`}
                className="flex min-w-0 flex-col justify-between rounded-control bg-surface-subtle p-3"
              >
                <dt className="text-metadata font-medium text-secondary leading-tight">{label}</dt>
                <dd className="mt-2 text-3xl font-extrabold tracking-tight text-primary">
                  {metric.link.route ? (
                    <Link
                      to={metric.link.route}
                      aria-label={`${label}: ${value}`}
                      className="text-action underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus transition-colors"
                    >
                      {value}
                    </Link>
                  ) : (
                    value
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : null}
      <div>
        <Link to={`/w/${workspace.id}/more/reports`} className={LINK}>
          {t("home.numbers.openReport")}
        </Link>
      </div>
    </Section>
  );
}
