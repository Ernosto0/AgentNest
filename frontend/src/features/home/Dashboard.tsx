import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReportMetric, SocialAccount } from "@/api/types";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, CriticalIcon, ImageIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMeta } from "@/features/auth/hooks";
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
    <Card className="flex flex-col gap-4 rounded-2xl border border-border/80 bg-surface p-5 md:p-6 shadow-card-modern" aria-labelledby={id}>
      <h2 id={id} className="type-section font-heading font-bold tracking-tight text-primary flex items-center justify-between text-base sm:text-lg">
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
      <StatusStrip accounts={accounts.data} />
      <Banners accounts={accounts.data ?? []} canReconnect={role === "owner"} />
      <Attention metrics={metrics} pending={report.isPending} error={report.error} />
      <Upcoming />
      <Failures />
      <Numbers report={report.data} metrics={metrics} />
    </div>
  );
}

const STATUS_ICON = {
  connected: { Icon: CheckIcon, tone: "text-success" },
  degraded: { Icon: AlertIcon, tone: "text-attention" },
  needs_reauth: { Icon: CriticalIcon, tone: "text-danger" },
} as const;

// `accounts` is undefined until they are loaded: "no account" must not flash first.
function StatusStrip({ accounts }: { accounts: SocialAccount[] | undefined }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const simulated = workspace.is_demo || (accounts ?? []).some((a) => a.is_simulated);
  return (
    <ul aria-label={t("home.statusLabel")} className="flex flex-wrap items-center gap-2 text-metadata">
      {accounts === undefined ? null : accounts.length === 0 ? (
        <li
          data-testid="home-connection"
          className="inline-flex items-center gap-2 rounded-full bg-surface px-3.5 py-1 font-medium text-secondary border border-border/80 shadow-2xs"
        >
          <span className="h-2 w-2 rounded-full bg-secondary/40" />
          <span>{t("home.connection")}: {t("home.noAccount")}</span>
        </li>
      ) : (
        accounts.map((account) => {
          const known = STATUS_ICON[account.status as keyof typeof STATUS_ICON];
          return (
            <li
              key={account.id}
              data-testid="home-connection"
              data-status={account.status}
              className="inline-flex items-center gap-2 rounded-full bg-surface px-3.5 py-1 font-medium text-primary border border-border/80 shadow-2xs"
            >
              <span className={`h-2 w-2 rounded-full ${account.status === "connected" ? "bg-success" : account.status === "degraded" ? "bg-attention" : "bg-danger"}`} />
              {known ? <known.Icon className={`text-base ${known.tone}`} /> : null}
              <span>
                {t("home.connection")}
                {account.username ? ` @${account.username}` : ""}:{" "}
                {t(`automation.accountStatus.${account.status}`, { defaultValue: account.status })}
              </span>
            </li>
          );
        })
      )}
      {simulated ? (
        <li>
          <SimulatedBadge />
        </li>
      ) : null}
      {meta.data ? (
        <li
          data-testid="home-ai-mode"
          className="inline-flex items-center gap-2 rounded-full bg-surface px-3.5 py-1 font-medium text-primary border border-border/80 shadow-2xs"
        >
          <span className="h-2 w-2 rounded-full bg-action" />
          {meta.data.llm_mode === "fake" ? t("aiMode.offline") : t("home.aiOnline")}
        </li>
      ) : null}
    </ul>
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

function Attention({
  metrics,
  pending,
  error,
}: {
  metrics: Map<string, ReportMetric>;
  pending: boolean;
  error: Error | null;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const base = `/w/${workspace.id}`;
  // The report decides what a person may see (staff: inbox numbers only), so a missing metric is no card.
  const cards = [
    { key: "pending_approvals_now", label: t("home.attention.approvals"), to: `${base}/approvals` },
    { key: "attention_now", label: t("home.attention.needsHuman"), to: `${base}/inbox` },
    { key: "content_failed", label: t("home.attention.failures"), to: `${base}/content?tab=problems` },
    { key: "content_on_hold_now", label: t("home.attention.onHold"), to: `${base}/content?tab=problems` },
  ]
    .filter((card) => metrics.has(card.key))
    .map((card) => ({ ...card, count: metrics.get(card.key)?.value ?? 0 }));
  const nothing = cards.every((card) => card.count === 0);

  return (
    <Section id="home-attention" title={t("home.attention.title")}>
      {error ? <ErrorMessage error={error} /> : null}
      {pending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
      {!pending && !error && nothing ? (
        <div data-testid="attention-none" className="flex items-center gap-3 rounded-xl bg-success-subtle/70 border border-success/30 p-4 text-body text-success">
          <CheckIcon className="text-xl text-success shrink-0" />
          <span className="font-medium text-primary">{t("home.attention.none")}</span>
        </div>
      ) : null}
      {!nothing ? (
        <ul className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          {cards.map((card) => (
            <li key={card.key} data-testid={`attention-${card.key}`}>
              <Link
                to={card.to}
                className={`group flex min-h-16 items-center justify-between gap-4 rounded-xl px-4 py-3.5 border transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                  card.count > 0
                    ? "bg-amber-500/10 text-primary border-amber-500/40 shadow-xs hover:border-amber-600 hover:shadow-card-hover hover:translate-y-[-1px]"
                    : "bg-surface text-primary border-border hover:bg-surface-subtle hover:border-border"
                }`}
              >
                <span className="font-semibold text-body">{card.label}</span>
                <span
                  className={`flex h-9 min-w-9 items-center justify-center rounded-lg px-2.5 text-xl font-bold tracking-tight transition-transform group-hover:scale-105 ${
                    card.count > 0 ? "bg-attention text-white shadow-xs" : "bg-surface-subtle text-secondary border border-border/70"
                  }`}
                >
                  {card.count}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Section>
  );
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
        <ul className="flex flex-col gap-2.5">
          {upcoming.data.slice(0, 3).map((item) => (
            <li
              key={item.id}
              className="group flex items-center justify-between gap-3 rounded-xl border border-border/80 bg-surface p-3.5 transition-all duration-150 hover:bg-surface-subtle/70 hover:border-action/30 hover:shadow-2xs"
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
        </ul>
      ) : null}
      <div>
        <Link to={`/w/${workspace.id}/content?tab=scheduled`} className={LINK}>
          {t("home.upcoming.all")}
        </Link>
      </div>
    </Section>
  );
}

function Failures() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const failures = useRecentFailures(workspace.id);
  return (
    <Section id="home-failures" title={t("home.failures.title")}>
      {failures.isError ? <ErrorMessage error={failures.error} /> : null}
      {failures.isPending ? <p className="text-body text-secondary">{t("common.loading")}</p> : null}
      {failures.data && failures.data.length === 0 ? (
        <p data-testid="failures-empty" className="text-body text-secondary">
          {t("home.failures.empty")}
        </p>
      ) : null}
      {failures.data && failures.data.length > 0 ? (
        <ul className="flex flex-col gap-2.5">
          {failures.data.slice(0, 3).map((item) => {
            const code = item.last_error_code ?? "";
            const known = code !== "" ? t(`errors.${code}.what`, { defaultValue: "" }) : "";
            return (
              <li
                key={item.id}
                className="flex flex-col gap-1.5 rounded-xl border border-danger/30 bg-danger-subtle/80 p-3.5 transition-all shadow-2xs"
              >
                <Link
                  to={`/w/${workspace.id}/content/${item.id}`}
                  className="font-semibold text-danger hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                >
                  {item.title}
                </Link>
                <span className="text-body text-primary font-medium">
                  {known !== "" ? known : t("content.failure.unknown.what")}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
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
            const value = formatValue(metric.value ?? 0, i18n.language);
            return (
              <div
                key={metric.key}
                data-testid={`number-${metric.key}`}
                className="group relative flex flex-col justify-between overflow-hidden rounded-xl bg-gradient-to-b from-surface to-surface-subtle/50 p-4 border border-border/80 shadow-2xs transition-all duration-150 hover:bg-surface hover:border-action/40 hover:shadow-card-hover hover:translate-y-[-1px]"
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
