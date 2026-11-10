import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, ChevronRightIcon, InfoIcon, PauseIcon, PlayIcon, SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useMeta } from "@/features/auth/hooks";
import { newRequestId } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS } from "./AgentParts";
import { useChangeAgent, type Schema } from "./hooks";
import { IN_PROGRESS_RUNS, TONE_DOT, TONE_PILL, type Tone } from "./presentation";

type Overview = Schema<"AgentOverview">;

/**
 * Who the assistant works for, whether it may start new work, and what waits on the owner.
 * "Active" means it accepts new work; only a non-zero `running` count says it is working now.
 */
export function AssistantHero({
  account,
  data,
  owner,
  picker,
}: {
  account: SocialAccount;
  data: Overview;
  owner: boolean;
  picker?: ReactNode;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ws = workspace.id;
  const meta = useMeta();
  const change = useChangeAgent(ws, account.id);
  const [confirm, setConfirm] = useState(false);
  const connected = account.status === "connected";
  const legacy = data.controller_mode === "legacy";
  const running = data.session_counts.running ?? 0;
  const state = legacy ? "legacy" : (["active", "paused", "inactive"].includes(data.state) ? data.state : "inactive");
  const tone: Tone = state === "active" ? "success" : state === "paused" ? "attention" : "neutral";
  const sentence =
    state === "active" && running > 0 ? t("agent.hero.working", { count: running }) : t(`agent.hero.sentence.${state}`);

  return (
    <section
      aria-labelledby="agent-hero-title"
      data-testid="agent-hero"
      className="flex min-w-0 flex-col gap-4 rounded-2xl bg-assistant p-4 sm:p-5"
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="flex min-w-0 flex-1 basis-72 items-start gap-3.5">
          <span aria-hidden="true" className="relative mt-0.5 flex size-12 shrink-0 items-center justify-center rounded-full bg-action font-heading text-lg font-bold text-on-action uppercase">
            {(account.username ?? "?").slice(0, 1)}
            <span className="absolute -right-1 -bottom-1 flex size-5 items-center justify-center rounded-full bg-assistant text-[0.6875rem] text-action ring-2 ring-assistant">
              <SparkIcon />
            </span>
          </span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-secondary">{t("agent.hero.eyebrow")}</p>
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <h2 id="agent-hero-title" className="min-w-0 font-heading text-xl leading-tight font-bold tracking-tight text-primary [overflow-wrap:anywhere]">
                @{account.username ?? t("agent.account")}
              </h2>
              <span data-testid="agent-state" className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONE_PILL[tone]}`}>
                <span aria-hidden="true" className={`size-1.5 rounded-full ${TONE_DOT[tone]}`} />
                {t(`agent.hero.state.${state}`)}
              </span>
              {data.is_simulated ? <SimulatedBadge compact /> : null}
              {meta.data?.llm_mode === "fake" ? (
                <span className="rounded-full bg-surface/80 px-2 text-[11px] leading-5 font-semibold text-secondary">{t("aiMode.offline")}</span>
              ) : null}
            </div>
            <p role="status" className="mt-1 flex items-center gap-2 text-body text-primary">
              {state === "active" && running > 0 ? (
                <span aria-hidden="true" className="relative flex size-2 shrink-0">
                  <span className="absolute inline-flex size-full rounded-full bg-success opacity-60 motion-safe:animate-ping" />
                  <span className="relative inline-flex size-2 rounded-full bg-success" />
                </span>
              ) : null}
              <span>{sentence}</span>
            </p>
            {legacy ? (
              <Link to={`/w/${ws}/more/automation`} className={`mt-1 inline-flex min-h-9 items-center gap-0.5 rounded-control text-metadata font-semibold text-action hover:underline ${FOCUS}`}>
                {t("agent.legacySettings")}
                <ChevronRightIcon aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </div>

        <div className="flex w-full min-w-0 flex-col gap-2 sm:w-80 sm:items-end">
          {picker}
          {owner ? (
            legacy ? (
              confirm ? null : (
                <Button disabled={!connected || change.isPending} onClick={() => setConfirm(true)} className="w-full sm:w-auto">
                  <SparkIcon aria-hidden="true" />
                  {t("agent.enable")}
                </Button>
              )
            ) : (
              <Button
                variant={data.state === "active" ? "secondary" : "primary"}
                pending={change.isPending}
                disabled={data.state === "paused" && !connected}
                className="w-full sm:w-auto"
                onClick={() =>
                  change.mutate({
                    command: data.state === "active" ? "pause" : "resume",
                    version: data.config_version,
                    requestId: newRequestId(),
                  })
                }
              >
                {change.isPending ? null : data.state === "active" ? <PauseIcon aria-hidden="true" /> : <PlayIcon aria-hidden="true" />}
                {t(data.state === "active" ? "agent.pause" : "agent.resume")}
              </Button>
            )
          ) : (
            <p className="text-metadata text-secondary sm:text-right">{t("agent.ownerOnly")}</p>
          )}
          {legacy ? null : (
            <p className="flex items-start gap-1.5 text-xs leading-5 text-secondary">
              <InfoIcon aria-hidden="true" className="mt-0.5 shrink-0" />
              <span>{t("agent.pauseWarning")}</span>
            </p>
          )}
        </div>
      </div>

      {!connected ? (
        <div role="status" className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-danger-subtle px-4 py-3">
          <AlertIcon aria-hidden="true" className="shrink-0 text-lg text-danger" />
          <p className="min-w-0 flex-1 basis-56 text-body font-medium text-primary">{t("agent.connectionRequired")}</p>
          <Link to={`/w/${ws}/more/settings/connections`} className={`inline-flex min-h-10 items-center rounded-control px-1 text-metadata font-semibold text-danger hover:underline ${FOCUS}`}>
            {t("automation.manageConnection")}
          </Link>
        </div>
      ) : null}

      {confirm && legacy ? (
        <div className="flex flex-col gap-3 rounded-xl bg-surface px-4 py-3.5 ring-1 ring-attention/30">
          <p className="flex items-start gap-2 text-body text-primary">
            <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0 text-attention" />
            <span>{t("agent.migrationWarning")}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              pending={change.isPending}
              onClick={() =>
                change.mutate(
                  { command: "activate", version: data.config_version, requestId: newRequestId(), mode: "agent" },
                  { onSuccess: () => setConfirm(false) },
                )
              }
            >
              {t("agent.confirmController")}
            </Button>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}
      {change.error ? <ErrorMessage error={change.error} /> : null}

      <WorkCounts data={data} accountId={account.id} />
    </section>
  );
}


type Tile = { key: string; value: number; tone: "attention" | "danger" | null; to?: string; linkText?: string; caption?: string };

/** What waits on the owner (each links to where it is handled), then the assistant's run totals. */
function WorkCounts({ data, accountId }: { data: Overview; accountId: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ws = workspace.id;
  const counts = data.session_counts;
  const inProgress = IN_PROGRESS_RUNS.reduce((sum, state) => sum + (counts[state] ?? 0), 0);
  const breakdown = IN_PROGRESS_RUNS.filter((state) => (counts[state] ?? 0) > 0)
    .slice(0, 2)
    .map((state) => t(`agent.runCount.${state}`, { count: counts[state] }))
    .join(" · ");
  const failed = counts.failed ?? 0;

  const waiting: Tile[] = [
    { key: "approvals", value: data.pending_approvals, tone: data.pending_approvals > 0 ? "attention" : null, to: `/w/${ws}/approvals`, linkText: t("agent.counts.approvalsLink") },
    { key: "questions", value: data.pending_questions, tone: data.pending_questions > 0 ? "attention" : null, to: `/w/${ws}/more/agent/questions?account=${accountId}`, linkText: t("agent.counts.questionsLink") },
  ];
  const work: Tile[] = [
    { key: "inProgress", value: inProgress, tone: null, caption: breakdown || undefined },
    { key: "completed", value: counts.completed ?? 0, tone: null },
    { key: "failed", value: failed, tone: failed > 0 ? "danger" : null },
  ];

  return (
    <div className="flex flex-col gap-2">
      <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <CountGroup id="agent-counts-waiting" title={t("agent.counts.waitingTitle")} tiles={waiting} />
        <CountGroup id="agent-counts-work" title={t("agent.counts.workTitle")} tiles={work} />
      </div>
      <p className="text-xs text-secondary">{t("agent.counts.note")}</p>
    </div>
  );
}

function CountGroup({ id, title, tiles }: { id: string; title: string; tiles: Tile[] }) {
  const { t } = useTranslation();
  const bg = { attention: "bg-attention-subtle", danger: "bg-danger-subtle" } as const;
  const label = { attention: "text-attention", danger: "text-danger" } as const;
  return (
    <div role="group" aria-labelledby={id} className="flex min-w-0 flex-col gap-1.5">
      <h3 id={id} className="text-xs font-semibold text-secondary">{title}</h3>
      <dl
        className={`grid gap-px overflow-hidden rounded-xl bg-border ring-1 ring-border ${tiles.length === 3 ? "grid-cols-3" : "grid-cols-2"}`}
      >
        {tiles.map((tile) => (
          <div
            key={tile.key}
            data-testid={`agent-count-${tile.key}`}
            className={`group relative flex min-w-0 flex-col px-3 py-2.5 transition-colors sm:px-4 ${tile.tone ? bg[tile.tone] : "bg-surface"} ${
              tile.to ? "hover:brightness-[0.98]" : ""
            }`}
          >
            <dt className={`text-xs font-medium [overflow-wrap:anywhere] ${tile.tone ? label[tile.tone] : "text-secondary"}`}>{t(`agent.counts.${tile.key}`)}</dt>
            <dd className={`font-heading text-[1.625rem] leading-8 font-bold tracking-tight tabular-nums ${tile.value === 0 ? "text-secondary" : "text-primary"}`}>
              {tile.value}
            </dd>
            {tile.to ? (
              <dd className="text-xs leading-5">
                <Link
                  to={tile.to}
                  className={`inline-flex items-center gap-0.5 rounded-sm font-semibold text-action after:absolute after:inset-0 after:content-[''] group-hover:underline ${FOCUS}`}
                >
                  {tile.linkText}
                  <ChevronRightIcon aria-hidden="true" className="shrink-0" />
                </Link>
              </dd>
            ) : tile.caption ? (
              <dd className="truncate text-xs leading-5 text-secondary" title={tile.caption}>{tile.caption}</dd>
            ) : null}
          </div>
        ))}
      </dl>
    </div>
  );
}
