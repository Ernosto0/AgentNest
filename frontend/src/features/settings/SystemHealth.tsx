import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { AccountStatusBadge } from "./AccountStatusBadge";
import { useErrorText, useLocalTime, useSystemHealth } from "./hooks";

function Row({ label, value, testId }: { label: string; value: ReactNode; testId?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate-700">{label}</dt>
      <dd className="text-right font-semibold" data-testid={testId}>
        {value}
      </dd>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-3" data-testid={id}>
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </Card>
  );
}

/** A duration in whole seconds, shown in the largest sensible unit. */
function useDuration() {
  const { t } = useTranslation();
  return (seconds: number) => {
    if (seconds < 60) return t("systemHealth.jobs.seconds", { count: seconds });
    if (seconds < 3600)
      return t("systemHealth.jobs.minutes", {
        count: Math.floor(seconds / 60),
      });
    return t("systemHealth.jobs.hours", { count: Math.floor(seconds / 3600) });
  };
}

/** What happened in the background in the last 24 hours (owner and manager): counts and codes only. */
export function SystemHealth() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const health = useSystemHealth(workspace.id);
  const errorText = useErrorText();
  const localTime = useLocalTime();
  const duration = useDuration();
  const number = new Intl.NumberFormat(i18n.language);

  const reason = (code: string | null | undefined) => {
    if (!code) return null;
    const { what } = errorText(code);
    return what !== "" ? what : t("systemHealth.unknownError");
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("systemHealth.title")}</h1>
        <p className="mt-1 text-slate-600">{t("systemHealth.intro")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" disabled={health.isFetching} onClick={() => void health.refetch()}>
          {health.isFetching ? t("systemHealth.refreshing") : t("systemHealth.refresh")}
        </Button>
        {health.data ? (
          <p className="text-sm text-slate-600" data-testid="health-generated-at">
            {t("systemHealth.generatedAt", {
              time: localTime(health.data.generated_at),
            })}
          </p>
        ) : null}
      </div>

      {health.isError ? <ErrorMessage error={health.error} /> : null}
      {health.isPending ? <p>{t("common.loading")}</p> : null}

      {health.data ? (
        <>
          <Section id="health-accounts" title={t("systemHealth.accounts.title")}>
            {health.data.accounts.length === 0 ? <p>{t("systemHealth.accounts.none")}</p> : null}
            <ul className="flex flex-col gap-3">
              {health.data.accounts.map((account) => (
                <li key={account.id} className="flex flex-col gap-1" data-testid="health-account">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">@{account.username ?? account.id}</span>
                    <AccountStatusBadge status={account.status} />
                    {account.is_simulated ? <SimulatedBadge /> : null}
                  </span>
                  {account.last_error_code ? (
                    <span className="text-sm text-slate-700" data-testid="health-account-error">
                      {reason(account.last_error_code)}
                    </span>
                  ) : null}
                  {account.status === "degraded" && account.degraded_until ? (
                    <span className="text-sm text-amber-900">
                      {t("systemHealth.accounts.degradedUntil", {
                        time: localTime(account.degraded_until),
                      })}
                    </span>
                  ) : null}
                  {account.connection_expires_at ? (
                    <span className="text-sm text-slate-600">
                      {t("systemHealth.accounts.expires", {
                        time: localTime(account.connection_expires_at),
                      })}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
            <Link
              to={`/w/${workspace.id}/more/settings/connections`}
              className="text-sm font-semibold text-indigo-700 underline underline-offset-2"
            >
              {t("systemHealth.accounts.manage")}
            </Link>
          </Section>

          <Section id="health-operations" title={t("systemHealth.operations.title")}>
            {health.data.operations.counts.length === 0 ? <p>{t("systemHealth.operations.none")}</p> : null}
            <dl className="flex flex-col gap-1">
              {health.data.operations.counts.map((row) => (
                <Row
                  key={`${row.type}:${row.status}`}
                  testId={`op-count-${row.type}-${row.status}`}
                  label={t("systemHealth.operations.row", {
                    type: t(`systemHealth.operations.type.${row.type}`, {
                      defaultValue: row.type,
                    }),
                    status: t(`systemHealth.operations.status.${row.status}`, {
                      defaultValue: row.status,
                    }),
                  })}
                  value={number.format(row.count)}
                />
              ))}
            </dl>
            <h3 className="text-sm font-semibold text-slate-700">{t("systemHealth.operations.failures")}</h3>
            {health.data.operations.latest_failures.length === 0 ? (
              <p className="text-sm">{t("systemHealth.operations.noFailures")}</p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm">
                {health.data.operations.latest_failures.map((failure) => (
                  <li key={failure.id} data-testid="health-failure" className="flex flex-col">
                    <span className="flex flex-wrap items-center gap-2 font-medium">
                      {t("systemHealth.operations.row", {
                        type: t(`systemHealth.operations.type.${failure.type}`, { defaultValue: failure.type }),
                        status: t(`systemHealth.operations.status.${failure.status}`, {
                          defaultValue: failure.status,
                        }),
                      })}
                      {failure.is_simulated ? <SimulatedBadge /> : null}
                    </span>
                    <span className="text-slate-700">{reason(failure.last_error_code) ?? ""}</span>
                    <span className="text-slate-600">{localTime(failure.occurred_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section id="health-jobs" title={t("systemHealth.jobs.title")}>
            <dl className="flex flex-col gap-1">
              <Row
                label={t("systemHealth.jobs.queued")}
                testId="jobs-queued"
                value={number.format(health.data.jobs.queued)}
              />
              <Row
                label={t("systemHealth.jobs.oldest")}
                testId="jobs-oldest"
                value={
                  health.data.jobs.oldest_queued_age_seconds === null
                    ? t("systemHealth.jobs.oldestNone")
                    : duration(health.data.jobs.oldest_queued_age_seconds)
                }
              />
              <Row
                label={t("systemHealth.jobs.dead")}
                testId="jobs-dead"
                value={number.format(health.data.jobs.dead_24h)}
              />
            </dl>
          </Section>

          <Section id="health-webhooks" title={t("systemHealth.webhooks.title")}>
            <dl className="flex flex-col gap-1">
              <Row
                label={t("systemHealth.webhooks.received")}
                testId="webhooks-received"
                value={number.format(health.data.webhooks.received_24h)}
              />
              <Row
                label={t("systemHealth.webhooks.ignored")}
                testId="webhooks-ignored"
                value={number.format(health.data.webhooks.ignored_24h)}
              />
              <Row
                label={t("systemHealth.webhooks.failed")}
                testId="webhooks-failed"
                value={number.format(health.data.webhooks.failed_24h)}
              />
              <Row
                label={t("systemHealth.webhooks.signature")}
                testId="webhooks-signature"
                value={number.format(health.data.webhooks.signature_failures_24h_system_wide)}
              />
            </dl>
            <p className="text-sm text-slate-600">{t("systemHealth.webhooks.signatureHint")}</p>
          </Section>

          <Section id="health-ai" title={t("systemHealth.ai.title")}>
            {health.data.ai.total === 0 ? <p>{t("systemHealth.ai.none")}</p> : null}
            <ul className="flex flex-col gap-1 text-sm">
              {health.data.ai.runs.map((run) => (
                <li key={`${run.task}:${run.status}`} className="flex justify-between gap-3">
                  <span>
                    {t(`systemHealth.ai.task.${run.task}`, {
                      defaultValue: run.task,
                    })}{" "}
                    ·{" "}
                    {t(`systemHealth.ai.status.${run.status}`, {
                      defaultValue: run.status,
                    })}
                  </span>
                  <span className="font-semibold">{number.format(run.count)}</span>
                </li>
              ))}
            </ul>
            <dl className="flex flex-col gap-1">
              <Row label={t("systemHealth.ai.total")} testId="ai-total" value={number.format(health.data.ai.total)} />
              <Row
                label={t("systemHealth.ai.failed")}
                testId="ai-failed"
                value={number.format(health.data.ai.failed)}
              />
              <Row
                label={t("systemHealth.ai.failureRate")}
                testId="ai-failure-rate"
                value={new Intl.NumberFormat(i18n.language, {
                  style: "percent",
                  maximumFractionDigits: 1,
                }).format(health.data.ai.failure_rate)}
              />
              <Row
                label={t("systemHealth.ai.input")}
                testId="ai-input"
                value={number.format(health.data.ai.input_units)}
              />
              <Row
                label={t("systemHealth.ai.output")}
                testId="ai-output"
                value={number.format(health.data.ai.output_units)}
              />
              <Row
                label={t("systemHealth.ai.cost")}
                testId="ai-cost"
                value={
                  health.data.ai.estimated_cost_usd === null
                    ? t("systemHealth.ai.costNone")
                    : new Intl.NumberFormat(i18n.language, {
                        style: "currency",
                        currency: "USD",
                        maximumFractionDigits: 4,
                      }).format(health.data.ai.estimated_cost_usd)
                }
              />
              <Row
                label={t("systemHealth.ai.budget")}
                testId="ai-budget"
                value={t("systemHealth.ai.budgetValue", {
                  used: number.format(health.data.ai.budget_used),
                  limit: number.format(health.data.ai.budget_limit),
                })}
              />
            </dl>
          </Section>
        </>
      ) : null}
    </div>
  );
}
