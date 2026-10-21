import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ReportMetric, SocialAccount } from "@/api/types";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CheckIcon, CriticalIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMeta } from "@/features/auth/hooks";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { formatValue } from "@/features/reports/format";
import { useDailyReport } from "@/features/reports/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useRecentFailures, useUpcomingPosts } from "./hooks";

const LINK =
  "inline-flex min-h-11 items-center font-medium text-indigo-800 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-3" aria-labelledby={id}>
      <h2 id={id} className="text-lg font-medium">
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
    <>
      <StatusStrip accounts={accounts.data} />
      <Banners accounts={accounts.data ?? []} canReconnect={role === "owner"} />
      <Attention metrics={metrics} pending={report.isPending} error={report.error} />
      <Upcoming />
      <Failures />
      <Numbers report={report.data} metrics={metrics} />
    </>
  );
}

const STATUS_ICON = {
  connected: { Icon: CheckIcon, tone: "text-green-800" },
  degraded: { Icon: AlertIcon, tone: "text-amber-800" },
  needs_reauth: { Icon: CriticalIcon, tone: "text-red-800" },
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
        <li data-testid="home-connection" className="rounded-full bg-slate-100 px-3 py-1 text-slate-800">
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
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-slate-800"
            >
              {known ? <known.Icon className={`text-base ${known.tone}`} /> : null}
              {t("home.connection")}
              {account.username ? ` @${account.username}` : ""}:{" "}
              {t(`automation.accountStatus.${account.status}`, { defaultValue: account.status })}
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
        <li data-testid="home-ai-mode" className="rounded-full bg-slate-100 px-3 py-1 text-slate-800">
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
          className="flex flex-col gap-2 rounded-xl bg-red-50 p-4 text-red-950 ring-1 ring-red-500"
        >
          <p className="flex items-start gap-2 font-medium">
            <CriticalIcon className="mt-1 shrink-0 text-xl" />
            {t("home.banner.needs_reauth")}
          </p>
          {canReconnect ? (
            <Link to={`/w/${workspace.id}/more/settings/connections`} className={LINK}>
              {t("home.banner.reconnect")}
            </Link>
          ) : (
            <p className="text-sm">{t("automation.ownerOnly")}</p>
          )}
        </div>
      ) : null}
      {degraded ? (
        <div
          role="status"
          data-testid="banner-degraded"
          className="flex items-start gap-2 rounded-xl bg-amber-50 p-4 font-medium text-amber-950 ring-1 ring-amber-500"
        >
          <AlertIcon className="mt-1 shrink-0 text-xl" />
          {t("home.banner.degraded")}
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
  const { t, i18n } = useTranslation();
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
        <p data-testid="attention-none" className="text-slate-700">
          {t("home.attention.none")}
        </p>
      ) : null}
      {!nothing ? (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {cards.map((card) => (
            <li key={card.key} data-testid={`attention-${card.key}`}>
              <Link
                to={card.to}
                aria-label={`${card.label}: ${formatValue(card.count, i18n.language)}`}
                className={`flex min-h-14 items-center justify-between gap-3 rounded-lg px-4 py-2 ring-1 focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                  card.count > 0
                    ? "bg-amber-50 text-amber-950 ring-amber-400"
                    : "bg-white text-slate-700 ring-slate-200"
                }`}
              >
                <span>{card.label}</span>
                <span className="text-xl font-semibold">{card.count}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Section>
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
        <div data-testid="upcoming-empty">
          <p className="font-medium text-slate-900">{t("home.upcoming.empty")}</p>
          <p className="text-sm text-slate-600">{t("home.upcoming.emptyHint")}</p>
        </div>
      ) : null}
      {upcoming.data && upcoming.data.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {upcoming.data.slice(0, 3).map((item) => (
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-2">
              <Link to={`/w/${workspace.id}/content/${item.id}`} className={LINK}>
                {item.title}
              </Link>
              <span className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
                {item.scheduled_at
                  ? new Date(item.scheduled_at).toLocaleString(i18n.language, {
                      dateStyle: "short",
                      timeStyle: "short",
                      timeZone: workspace.timezone,
                    })
                  : null}
                {item.is_simulated ? <SimulatedBadge /> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <Link to={`/w/${workspace.id}/content?tab=scheduled`} className={LINK}>
        {t("home.upcoming.all")}
      </Link>
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
        <p data-testid="failures-empty" className="text-slate-700">
          {t("home.failures.empty")}
        </p>
      ) : null}
      {failures.data && failures.data.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {failures.data.slice(0, 3).map((item) => {
            const code = item.last_error_code ?? "";
            const known = code !== "" ? t(`errors.${code}.what`, { defaultValue: "" }) : "";
            return (
              <li key={item.id} className="flex flex-col">
                <Link to={`/w/${workspace.id}/content/${item.id}`} className={LINK}>
                  {item.title}
                </Link>
                <span className="text-sm text-slate-700">
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
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
          {report.is_partial ? <span>{t("home.numbers.asOf", { time: asOf })}</span> : null}
          {report.has_simulated_data ? <SimulatedBadge /> : null}
        </div>
      ) : null}
      {report && quiet ? (
        <p data-testid="numbers-empty" className="text-slate-700">
          {t("home.numbers.empty")}
        </p>
      ) : null}
      {report && !quiet ? (
        <dl className="grid grid-cols-2 gap-3">
          {shown.map((metric) => {
            const label = t(`reports.metrics.${metric.key}`);
            const value = formatValue(metric.value ?? 0, i18n.language);
            return (
              <div key={metric.key} data-testid={`number-${metric.key}`} className="rounded-lg bg-slate-50 p-3">
                <dt className="text-sm text-slate-700">{label}</dt>
                <dd className="text-2xl font-semibold">
                  {metric.link.route ? (
                    <Link
                      to={metric.link.route}
                      aria-label={`${label}: ${value}`}
                      className="text-indigo-800 underline underline-offset-2"
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
      <Link to={`/w/${workspace.id}/more/reports`} className={LINK}>
        {t("home.numbers.openReport")}
      </Link>
    </Section>
  );
}
