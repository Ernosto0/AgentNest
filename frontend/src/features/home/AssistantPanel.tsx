import { useState, type ComponentType, type SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  BookIcon,
  ClockIcon,
  ImageIcon,
  InboxIcon,
  LinkIcon,
  PauseIcon,
  PlayIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SparkIcon,
  UsersIcon,
} from "@/components/icons";
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

/** Activity groups from the audit log; an icon makes the kind of action scannable. */
const GROUP_ICON: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  messages: InboxIcon,
  replies: InboxIcon,
  approvals: ShieldCheckIcon,
  content: ImageIcon,
  knowledge: BookIcon,
  commands: SparkIcon,
  accounts: LinkIcon,
  members: UsersIcon,
  system: SettingsIcon,
};

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
    <Panel tone="assistant" aria-labelledby="home-assistant-title" data-testid="agent-status-card" className={`gap-4 ${className}`}>
      <PanelHeading
        id="home-assistant-title"
        icon={<SparkIcon />}
        iconTone="assistant"
        title={t("home.agentStatus.title")}
        meta={
          <>
            <span>{t("home.assistant.subtitle")}</span>
            {meta.data?.llm_mode === "fake" ? (
              <span className="rounded-full bg-surface/80 px-2 text-[11px] font-semibold text-secondary">{t("aiMode.offline")}</span>
            ) : null}
          </>
        }
        action={<PanelLink to={`/w/${workspace.id}/more/agent`}>{t("common.settings")}</PanelLink>}
      />

      <div className="flex flex-col gap-1.5">
        {error ? (
          <ErrorMessage error={error} />
        ) : pending ? (
          <SkeletonRows label={t("common.loading")} rows={1} />
        ) : activeAccounts.length === 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface/70 px-3.5 py-2.5">
            <p className="text-body text-secondary">{t("home.agentStatus.empty")}</p>
            {canControl ? (
              <Link
                to={`/w/${workspace.id}/more/settings/connections`}
                className={`inline-flex min-h-10 items-center gap-2 rounded-control bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
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
    <div className="flex flex-col gap-2 rounded-xl bg-surface/60 px-3 py-1.5" data-testid={`agent-row-${account.id}`}>
      <div className="flex min-h-9 min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="relative flex size-2 shrink-0" aria-hidden="true">
          {isActive ? <span className={`absolute inline-flex size-full rounded-full ${dot} opacity-60 motion-safe:animate-ping`} /> : null}
          <span className={`relative inline-flex size-2 rounded-full ${dot}`} />
        </span>
        <span className="min-w-0 truncate text-body font-semibold text-primary">@{account.username}</span>
        <span className={`inline-flex items-center rounded-full px-2 py-px text-[11px] font-semibold ${pill}`}>{stateLabel}</span>
        {overview?.is_simulated || account.is_simulated ? <SimulatedBadge compact /> : null}
        {overview && KNOWN_MODES.has(overview.controller_mode) ? (
          <span className="text-xs text-secondary">{t(`home.agentStatus.mode.${overview.controller_mode}`)}</span>
        ) : null}
        {activeSessions > 0 ? (
          <span className="text-xs font-medium text-primary">{t("home.agentStatus.sessions", { count: activeSessions })}</span>
        ) : null}
        {canToggle && confirming === null ? (
          <button
            type="button"
            onClick={() => setConfirming(isPaused ? "resume" : "pause")}
            disabled={changeAgent.isPending}
            className={`ml-auto inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-secondary transition-colors hover:bg-surface hover:text-primary ${FOCUS}`}
          >
            {isPaused ? <PlayIcon aria-hidden="true" /> : <PauseIcon aria-hidden="true" />}
            <span>{isPaused ? t("home.agentStatus.resume") : t("home.agentStatus.pause")}</span>
          </button>
        ) : null}
      </div>

      {canToggle && confirming ? (
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface px-3 py-2">
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
  const empty = activity.isSuccess && entries.length === 0;

  return (
    <div
      data-testid="activity-feed-card"
      role="group"
      aria-labelledby="home-activity-title"
      className={`flex flex-col rounded-xl bg-surface/70 ${empty ? "px-3.5 py-1" : "px-3.5 pt-1 pb-3"}`}
    >
      <div className="flex flex-wrap items-center gap-x-2">
        <h3 id="home-activity-title" className="flex shrink-0 items-center gap-2 text-xs font-semibold whitespace-nowrap text-secondary">
          <ClockIcon aria-hidden="true" className="text-sm" />
          {t("home.activity.title")}
        </h3>
        {empty ? (
          <p data-testid="activity-empty" className="order-3 basis-full pb-2 text-xs text-secondary sm:order-none sm:basis-auto sm:pb-0">
            <span aria-hidden="true" className="mr-2 hidden text-secondary/50 sm:inline">·</span>
            {t("home.activity.empty")}
          </p>
        ) : null}
        <PanelLink to={`/w/${workspace.id}/more/activity`} className="ml-auto text-xs">
          {t("home.activity.all")}
        </PanelLink>
      </div>
      {activity.error ? (
        <ErrorMessage error={activity.error} />
      ) : activity.isPending ? (
        <SkeletonRows label={t("common.loading")} rows={2} />
      ) : empty ? null : (
        <ol className="flex flex-col gap-0.5">
          {entries.map((entry) => {
            const Icon = GROUP_ICON[entry.group] ?? SparkIcon;
            const absolute = new Date(entry.occurred_at).toLocaleString(i18n.language, {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: workspace.timezone,
            });
            return (
              <li key={entry.id} className="flex min-w-0 items-start gap-2.5 py-1.5">
                <span aria-hidden="true" className="mt-px flex size-6 shrink-0 items-center justify-center rounded-md bg-assistant text-xs text-action">
                  <Icon />
                </span>
                <p className="min-w-0 flex-1 text-body leading-snug text-primary [overflow-wrap:anywhere]">
                  {entry.resource?.link ? (
                    <Link to={entry.resource.link} className={`rounded-sm underline-offset-2 hover:text-action hover:underline ${FOCUS}`}>
                      {entry.text}
                    </Link>
                  ) : (
                    entry.text
                  )}
                  {entry.is_simulated ? <SimulatedBadge compact className="ml-2 align-middle" /> : null}
                </p>
                <time dateTime={entry.occurred_at} title={absolute} className="mt-0.5 shrink-0 text-xs text-secondary tabular-nums">
                  {relativeTime(entry.occurred_at, i18n.language)}
                </time>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
