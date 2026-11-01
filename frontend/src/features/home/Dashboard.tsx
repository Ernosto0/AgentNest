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
  "inline-flex min-h-11 items-center font-medium text-indigo-800 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-4" aria-labelledby={id}>
      <h2 id={id} className="text-lg font-semibold tracking-tight text-slate-900">
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
  connected: { Icon: CheckIcon, tone: "text-green-700" },
  degraded: { Icon: AlertIcon, tone: "text-amber-700" },
  needs_reauth: { Icon: CriticalIcon, tone: "text-red-700" },
} as const;

// `accounts` is undefined until they are loaded: "no account" must not flash first.
function StatusStrip({ accounts }: { accounts: SocialAccount[] | undefined }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const simulated = workspace.is_demo || (accounts ?? []).some((a) => a.is_simulated);
  return (
    <ul aria-label={t("home.statusLabel")} className="flex flex-wrap items-center gap-2 text-sm">
      {accounts === undefined ? null : accounts.length === 0 ? (
        <li data-testid="home-connection" className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-800 ring-1 ring-slate-200">
          {t("home.connection")}: {t("home.noAccount")}
        </li>
      ) : (
        accounts.map((account) => {
          const known = STATUS_ICON[account.status as keyof typeof STATUS_ICON];
          return (
            <li
              key={account.id}
              data-testid="home-connection"
              data-status={account.status}
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-800 ring-1 ring-slate-200"
            >
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
        <li data-testid="home-ai-mode" className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-800 ring-1 ring-slate-200">
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
          className="flex flex-col gap-2 rounded-xl bg-red-50 p-4 text-red-950 ring-1 ring-red-400"
        >
          <p className="flex items-start gap-2 font-medium">
            <CriticalIcon className="mt-0.5 shrink-0 text-xl text-red-700" />
            <span>{t("home.banner.needs_reauth")}</span>
          </p>
          {canReconnect ? (
            <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK}>
              {t("home.banner.reconnect")}
            </Link>
          ) : (
            <p className="text-sm text-red-900">{t("automation.ownerOnly")}</p>
          )}
        </div>
      ) : null}
      {degraded ? (
        <div
          role="status"
          data-testid="banner-degraded"
          className="flex items-start gap-2 rounded-xl bg-amber-50 p-4 font-medium text-amber-950 ring-1 ring-amber-400"
        >
          <AlertIcon className="mt-0.5 shrink-0 text-xl text-amber-700" />
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
      {pending ? <p className="text-sm text-slate-600">{t("common.loading")}</p> : null}
      {!pending && !error && nothing ? (
        <p data-testid="attention-none" className="text-sm text-slate-700">
          {t("home.attention.none")}
        </p>
      ) : null}
      {!nothing ? (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {cards.map((card) => (
            <li key={card.key} data-testid={`attention-${card.key}`}>
              <Link
                to={card.to}
                className={`flex min-h-14 items-center justify-between gap-3 rounded-xl px-4 py-3 ring-1 transition-colors focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                  card.count > 0
                    ? "bg-amber-50/80 text-amber-950 ring-amber-300 hover:bg-amber-100"
                    : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                <span className="font-medium">{card.label}</span>
                <span className="text-2xl font-bold tracking-tight">{card.count}</span>
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
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-400" aria-hidden="true">
        <ImageIcon className="text-lg" />
      </div>
    );
  }
  if (preview.url) {
    return (
      <img
        src={preview.url}
        alt=""
        className="h-10 w-10 shrink-0 rounded-lg object-cover ring-1 ring-slate-200"
      />
    );
  }
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-400" aria-hidden="true">
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
      {upcoming.isPending ? <p className="text-sm text-slate-600">{t("common.loading")}</p> : null}
      {upcoming.data && upcoming.data.length === 0 ? (
        <div data-testid="upcoming-empty" className="flex flex-col gap-1">
          <p className="font-medium text-slate-900">{t("home.upcoming.empty")}</p>
          <p className="text-sm text-slate-600">{t("home.upcoming.emptyHint")}</p>
        </div>
      ) : null}
      {upcoming.data && upcoming.data.length > 0 ? (
        <ul className="flex flex-col gap-2.5">
          {upcoming.data.slice(0, 3).map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-200/80 bg-white p-3 hover:bg-slate-50/70"
            >
              <div className="flex items-center gap-3 min-w-0">
                <UpcomingThumbnail workspaceId={workspace.id} mediaId={item.media_asset_id} deleted={item.media_deleted} />
                <div className="flex flex-col min-w-0">
                  <Link
                    to={`/w/${workspace.id}/content/${item.id}`}
                    className="font-medium text-slate-900 truncate hover:text-indigo-600 focus-visible:outline-2 focus-visible:outline-indigo-600"
                  >
                    {item.title}
                  </Link>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
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
      {failures.isPending ? <p className="text-sm text-slate-600">{t("common.loading")}</p> : null}
      {failures.data && failures.data.length === 0 ? (
        <p data-testid="failures-empty" className="text-sm text-slate-700">
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
                className="flex flex-col gap-1 rounded-lg border border-red-200/80 bg-red-50/50 p-3"
              >
                <Link
                  to={`/w/${workspace.id}/content/${item.id}`}
                  className="font-medium text-red-950 hover:underline focus-visible:outline-2 focus-visible:outline-indigo-600"
                >
                  {item.title}
                </Link>
                <span className="text-sm text-red-900">
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
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          {report.is_partial ? <span>{t("home.numbers.asOf", { time: asOf })}</span> : null}
          {report.has_simulated_data ? <SimulatedBadge /> : null}
        </div>
      ) : null}
      {report && quiet ? (
        <p data-testid="numbers-empty" className="text-sm text-slate-700">
          {t("home.numbers.empty")}
        </p>
      ) : null}
      {report && !quiet ? (
        <dl className="grid grid-cols-2 gap-3">
          {shown.map((metric) => {
            const label = t(`reports.metrics.${metric.key}`);
            const value = formatValue(metric.value ?? 0, i18n.language);
            return (
              <div key={metric.key} data-testid={`number-${metric.key}`} className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/80">
                <dt className="text-xs font-medium text-slate-600">{label}</dt>
                <dd className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                  {metric.link.route ? (
                    <Link
                      to={metric.link.route}
                      aria-label={`${label}: ${value}`}
                      className="text-indigo-800 underline underline-offset-2 hover:text-indigo-900"
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
