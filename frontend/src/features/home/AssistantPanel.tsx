import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { LinkIcon, PauseIcon, PlayIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useChangeAgent } from "@/features/agent/hooks";
import { useMeta } from "@/features/auth/hooks";
import { CommandBar } from "@/features/commands/CommandBar";
import { newRequestId } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";
import { useRecentAgentActivity, type useAgentOverviews } from "./hooks";

const KNOWN_MODES = new Set(["agent", "legacy"]);
const ACTIVITY_SHOWN = 4;

/**
 * The assistant as the centre of Today: who it works for and in what state, the request
 * entry (existing command semantics), and what it did most recently.
 */
export function AssistantPanel({
  accounts,
  overviews,
  canControl,
  pending,
  error,
  className = "",
}: {
  accounts: SocialAccount[];
  overviews: ReturnType<typeof useAgentOverviews>;
  canControl: boolean;
  pending: boolean;
  error: Error | null;
  className?: string;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const meta = useMeta();
  const activeAccounts = accounts.filter((a) => a.status !== "disconnected");

  return (
    <Panel tone="assistant" aria-labelledby="home-assistant-title" data-testid="agent-status-card" className={`gap-5 ${className}`}>
      <PanelHeading
        id="home-assistant-title"
        icon={<SparkIcon />}
        iconTone="assistant"
        title={t("home.agentStatus.title")}
        meta={
          <>
            <span>{t("home.assistant.subtitle")}</span>
            {meta.data?.llm_mode === "fake" ? (
              <span className="rounded-full bg-surface/80 px-2 py-px text-[11px] font-semibold text-secondary">{t("aiMode.offline")}</span>
            ) : null}
          </>
        }
        action={<PanelLink to={`/w/${workspace.id}/more/agent`}>{t("common.settings")}</PanelLink>}
      />

      <div className="flex flex-col gap-2">
        {error ? (
          <ErrorMessage error={error} />
        ) : pending ? (
          <SkeletonRows label={t("common.loading")} rows={1} />
        ) : activeAccounts.length === 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface/70 px-4 py-3">
            <p className="text-body text-secondary">{t("home.agentStatus.empty")}</p>
            {canControl ? (
              <Link
                to={`/w/${workspace.id}/more/settings/connections`}
                className={`inline-flex min-h-11 items-center gap-2 rounded-control bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
              >
                <LinkIcon aria-hidden="true" />
                {t("home.assistant.connect")}
              </Link>
            ) : null}
          </div>
        ) : (
          activeAccounts.map((account) => {
            // Overview queries are built from the same non-disconnected list, in the same order.
            const query = overviews[activeAccounts.indexOf(account)];
            return (
              <AccountAgentRow
                key={account.id}
                account={account}
                overview={query?.data}
                isPending={query?.isPending}
                unavailable={query?.isError ?? false}
                canControl={canControl}
              />
            );
          })
        )}
      </div>

      <CommandBar />

      <AgentActivity />
    </Panel>
  );
}

function AccountAgentRow({
  account,
  overview,
  isPending,
  unavailable,
  canControl,
}: {
  account: SocialAccount;
  overview: ReturnType<typeof useAgentOverviews>[number]["data"];
  isPending?: boolean;
  unavailable: boolean;
  canControl: boolean;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const changeAgent = useChangeAgent(workspace.id, account.id);
  const [confirming, setConfirming] = useState<"pause" | "resume" | null>(null);

  const isPaused = !unavailable && overview?.state === "paused";
  const isActive = !unavailable && !isPending && overview?.state === "active";
  const needsReauth = account.status === "needs_reauth";
  const activeSessions = overview?.session_counts?.active ?? 0;

  const act = (cmd: "pause" | "resume") => {
    if (!overview) return;
    changeAgent.mutate(
      { command: cmd, version: overview.config_version, requestId: newRequestId() },
      { onSuccess: () => setConfirming(null) },
    );
  };

  const stateLabel = needsReauth
    ? t("home.banner.needs_reauth")
    : unavailable
      ? t("core.unavailable")
      : isPending
        ? t("common.loading")
        : isPaused
          ? t("home.agentStatus.paused")
          : isActive
            ? t("home.agentStatus.active")
            : t("home.agentStatus.inactive");
  const dot = needsReauth ? "bg-danger" : isActive ? "bg-success" : isPaused ? "bg-control" : "bg-attention";
  const pill = needsReauth
    ? "bg-danger-subtle text-danger"
    : isActive
      ? "bg-success-subtle text-success"
      : "bg-surface-subtle text-secondary";
  const canToggle = canControl && overview && !unavailable && !isPending && (isActive || isPaused) && !needsReauth;

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-surface/75 px-3.5 py-2.5" data-testid={`agent-row-${account.id}`}>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
        <span className="relative flex size-2.5 shrink-0" aria-hidden="true">
          {isActive ? <span className={`absolute inline-flex size-full rounded-full ${dot} opacity-50 motion-safe:animate-ping`} /> : null}
          <span className={`relative inline-flex size-2.5 rounded-full ${dot}`} />
        </span>
        <span className="min-w-0 truncate font-semibold text-primary">@{account.username}</span>
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${pill}`}>{stateLabel}</span>
        {overview?.is_simulated || account.is_simulated ? <SimulatedBadge compact /> : null}
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 text-metadata text-secondary">
          {overview && KNOWN_MODES.has(overview.controller_mode) ? (
            <span>{t(`home.agentStatus.mode.${overview.controller_mode}`)}</span>
          ) : null}
          {activeSessions > 0 ? (
            <span className="font-medium text-primary">{t("home.agentStatus.sessions", { count: activeSessions })}</span>
          ) : null}
        </span>
        {canToggle && confirming === null ? (
          <Button
            variant="ghost"
            onClick={() => setConfirming(isPaused ? "resume" : "pause")}
            disabled={changeAgent.isPending}
            className="ml-auto px-3 text-metadata text-secondary hover:text-primary"
          >
            {isPaused ? <PlayIcon /> : <PauseIcon />}
            <span>{isPaused ? t("home.agentStatus.resume") : t("home.agentStatus.pause")}</span>
          </Button>
        ) : null}
      </div>

      {canToggle && confirming ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-subtle px-3 py-2">
          <span className="text-metadata text-primary">
            {confirming === "pause" ? t("home.agentStatus.confirmPause") : t("home.agentStatus.confirmResume")}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="secondary" onClick={() => setConfirming(null)} disabled={changeAgent.isPending} className="px-3 text-metadata">
              {t("common.cancel")}
            </Button>
            <Button
              variant={confirming === "pause" ? "danger" : "primary"}
              onClick={() => act(confirming)}
              pending={changeAgent.isPending}
              className="px-3 text-metadata"
            >
              {confirming === "pause" ? t("home.agentStatus.pause") : t("home.agentStatus.resume")}
            </Button>
          </div>
        </div>
      ) : null}
      {changeAgent.error ? <ErrorMessage error={changeAgent.error} /> : null}
    </div>
  );
}

function relativeTime(iso: string, language: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const format = new Intl.RelativeTimeFormat(language, { numeric: "auto", style: "short" });
  const abs = Math.abs(seconds);
  if (abs < 60) return format.format(0, "minute");
  if (abs < 3600) return format.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return format.format(Math.round(seconds / 3600), "hour");
  return format.format(Math.round(seconds / 86_400), "day");
}

/** The assistant's own recent actions (owners and managers; the activity API is not for staff). */
function AgentActivity() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const enabled = role !== "staff";
  const activity = useRecentAgentActivity(workspace.id, enabled);
  if (!enabled) return null;
  const entries = (activity.data ?? []).slice(0, ACTIVITY_SHOWN);

  return (
    <div data-testid="activity-feed-card" aria-labelledby="home-activity-title" role="group" className="flex flex-col gap-1 border-t border-action/10 pt-4">
      <div className="flex items-center justify-between gap-3">
        <h3 id="home-activity-title" className="text-xs font-bold uppercase tracking-wider text-secondary">
          {t("home.activity.title")}
        </h3>
        <PanelLink to={`/w/${workspace.id}/more/activity`}>{t("home.activity.all")}</PanelLink>
      </div>
      {activity.error ? (
        <ErrorMessage error={activity.error} />
      ) : activity.isPending ? (
        <SkeletonRows label={t("common.loading")} rows={2} />
      ) : entries.length === 0 ? (
        <p className="text-body text-secondary" data-testid="activity-empty">
          {t("home.activity.empty")}
        </p>
      ) : (
        <ol className="flex flex-col">
          {entries.map((entry, index) => {
            const absolute = new Date(entry.occurred_at).toLocaleString(i18n.language, {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: workspace.timezone,
            });
            return (
              <li key={entry.id} className="relative flex gap-3 pb-3 last:pb-0">
                {index < entries.length - 1 ? (
                  <span aria-hidden="true" className="absolute top-4 bottom-0 left-[4.5px] w-px bg-action/15" />
                ) : null}
                <span aria-hidden="true" className="mt-1.5 size-2.5 shrink-0 rounded-full border-2 border-action bg-assistant" />
                <div className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <p className="min-w-0 flex-1 basis-48 text-body leading-snug text-primary [overflow-wrap:anywhere]">
                    {entry.resource?.link ? (
                      <Link to={entry.resource.link} className={`rounded-sm underline-offset-2 hover:text-action hover:underline ${FOCUS}`}>
                        {entry.text}
                      </Link>
                    ) : (
                      entry.text
                    )}
                    {entry.is_simulated ? <SimulatedBadge compact className="ml-2 align-middle" /> : null}
                  </p>
                  <time dateTime={entry.occurred_at} title={absolute} className="shrink-0 text-xs text-secondary tabular-nums">
                    {relativeTime(entry.occurred_at, i18n.language)}
                  </time>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
