import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { PauseIcon, PlayIcon, SpinnerIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useChangeAgent } from "@/features/agent/hooks";
import { newRequestId } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import type { useAgentOverviews } from "./hooks";

export function AgentStatusCard({
  accounts,
  overviews,
  canControl,
  pending,
  error,
}: {
  accounts: SocialAccount[];
  overviews: ReturnType<typeof useAgentOverviews>;
  canControl: boolean;
  pending?: boolean;
  error?: Error | null;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const activeAccounts = accounts.filter((a) => a.status !== "disconnected");

  if (error || pending) {
    return (
      <Card className="flex flex-col gap-3 bg-surface p-5" data-testid="agent-status-card">
        <h2 className="type-section text-primary">{t("home.agentStatus.title")}</h2>
        {error ? <ErrorMessage error={error} /> : <p className="text-secondary">{t("common.loading")}</p>}
      </Card>
    );
  }

  if (activeAccounts.length === 0) {
    return (
      <Card className="flex flex-col gap-3 bg-surface p-5" data-testid="agent-status-card">
        <h2 className="type-section text-primary">{t("home.agentStatus.title")}</h2>
        <p className="text-body text-secondary">{t("home.agentStatus.empty")}</p>
        {canControl ? (
          <Link
            to={`/w/${workspace.id}/more/settings/connections`}
            className="inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover"
          >
            {t("home.banner.reconnect")}
          </Link>
        ) : null}
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-4 bg-surface p-5" data-testid="agent-status-card">
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <h2 className="type-section text-primary">{t("home.agentStatus.title")}</h2>
        <Link
          to={`/w/${workspace.id}/more/agent`}
          className="text-metadata font-medium text-action hover:underline"
        >
          {t("common.settings")}
        </Link>
      </div>

      <div className="flex flex-col divide-y divide-border/60">
        {activeAccounts.map((account, index) => {
          const overviewQuery = overviews[index];
          const overview = overviewQuery?.data;
          const isPending = overviewQuery?.isPending;

          return (
            <AccountAgentRow
              key={account.id}
              account={account}
              overview={overview}
              isPending={isPending}
              unavailable={overviewQuery?.isError ?? false}
              canControl={canControl}
            />
          );
        })}
      </div>
    </Card>
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

  const isPaused = overview?.state === "paused";
  const isActive = !unavailable && !isPending && overview?.state === "active";
  const needsReauth = account.status === "needs_reauth";

  const handleAction = (cmd: "pause" | "resume") => {
    if (!overview) return;
    changeAgent.mutate(
      {
        command: cmd,
        version: overview.config_version,
        requestId: newRequestId(),
      },
      {
        onSuccess: () => setConfirming(null),
      },
    );
  };

  const activeSessions = overview?.session_counts?.active ?? 0;

  return (
    <div className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0" data-testid={`agent-row-${account.id}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className={`inline-block size-2.5 rounded-full shrink-0 ${
              needsReauth
                ? "bg-danger"
                : isPaused
                ? "bg-secondary"
                : isActive
                ? "bg-success"
                : "bg-attention"
            }`}
            aria-hidden="true"
          />
          <span className="font-semibold text-primary truncate">@{account.username}</span>
          {overview?.is_simulated || account.is_simulated ? <SimulatedBadge /> : null}
        </div>

        {/* State badge */}
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
            needsReauth
              ? "bg-danger-subtle text-danger"
              : isActive && !unavailable
              ? "bg-success-subtle text-success"
              : "bg-surface-subtle text-secondary"
          }`}
        >
          {needsReauth
            ? t("home.banner.needs_reauth")
            : unavailable
            ? t("core.unavailable")
            : isPending
            ? t("common.loading")
            : isPaused
            ? t("home.agentStatus.paused")
            : isActive
            ? t("home.agentStatus.active")
            : t("home.agentStatus.inactive")}
        </span>
      </div>

      {/* Operational details */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-metadata text-secondary">
        {overview?.controller_mode ? (
          <span>{t(`agent.mode.${overview.controller_mode}`, { defaultValue: overview.controller_mode })}</span>
        ) : null}
        {activeSessions > 0 ? (
          <span className="font-medium text-primary">
            {t("home.agentStatus.sessions", { count: activeSessions })}
          </span>
        ) : null}
      </div>

      {/* Controls for Owner */}
      {changeAgent.error ? <ErrorMessage error={changeAgent.error} /> : null}
      {canControl && overview && !unavailable && !isPending && (isActive || isPaused) && !needsReauth ? (
        <div className="flex items-center gap-2 pt-1">
          {confirming === "pause" ? (
            <div className="flex items-center gap-2 bg-surface-subtle p-2 rounded-control w-full justify-between">
              <span className="text-metadata text-primary">{t("home.agentStatus.confirmPause")}</span>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="secondary"
                  onClick={() => setConfirming(null)}
                  disabled={changeAgent.isPending}
                  className="px-2.5 py-1 text-xs"
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handleAction("pause")}
                  disabled={changeAgent.isPending}
                  className="gap-1.5 px-2.5 py-1 text-xs"
                >
                  {changeAgent.isPending ? <SpinnerIcon className="motion-safe:animate-spin" /> : null}
                  <span>{t("home.agentStatus.pause")}</span>
                </Button>
              </div>
            </div>
          ) : confirming === "resume" ? (
            <div className="flex items-center gap-2 bg-surface-subtle p-2 rounded-control w-full justify-between">
              <span className="text-metadata text-primary">{t("home.agentStatus.confirmResume")}</span>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="secondary"
                  onClick={() => setConfirming(null)}
                  disabled={changeAgent.isPending}
                  className="px-2.5 py-1 text-xs"
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => handleAction("resume")}
                  disabled={changeAgent.isPending}
                  className="gap-1.5 px-2.5 py-1 text-xs"
                >
                  {changeAgent.isPending ? <SpinnerIcon className="motion-safe:animate-spin" /> : null}
                  <span>{t("home.agentStatus.resume")}</span>
                </Button>
              </div>
            </div>
          ) : (
            <div>
              {isPaused ? (
                <Button
                  variant="secondary"
                  onClick={() => setConfirming("resume")}
                  disabled={changeAgent.isPending || isPending}
                  className="gap-1.5 px-2.5 py-1 text-xs"
                >
                  <PlayIcon className="text-sm" />
                  <span>{t("home.agentStatus.resume")}</span>
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => setConfirming("pause")}
                  disabled={changeAgent.isPending || isPending}
                  className="gap-1.5 px-2.5 py-1 text-xs"
                >
                  <PauseIcon className="text-sm" />
                  <span>{t("home.agentStatus.pause")}</span>
                </Button>
              )}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
