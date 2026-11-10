import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CalendarIcon, CheckIcon, ChevronRightIcon, LinkIcon, SettingsIcon, ShieldCheckIcon, XIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { capabilityLabel } from "@/features/content/messages";
import { newRequestId } from "@/features/commands/hooks";
import { SkeletonRows } from "@/features/home/DashboardPanel";
import { useCalendarConnections } from "@/features/settings/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, ModeChip, SectionTitle, Surface } from "./AgentParts";
import { actionLabelKey, useChangeAgent, type Schema } from "./hooks";
import { CAPABILITY_GROUPS, KNOWN_CAPABILITIES, TONE_PILL, actionsForCapability, combinedMode } from "./presentation";

type Policy = Schema<"DelegationPolicy"> | null | undefined;

function QuietLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className={`group/link -mx-1 inline-flex min-h-10 items-center gap-0.5 rounded-control px-1 text-metadata font-semibold text-action ${FOCUS}`}>
      <span className="underline-offset-4 group-hover/link:underline">{children}</span>
      <ChevronRightIcon aria-hidden="true" className="transition-transform duration-150 group-hover/link:translate-x-0.5" />
    </Link>
  );
}

/**
 * What the connected Instagram account allows (provider grants), grouped by what an owner
 * recognises, with the assistant's own permission beside it. Availability and permission are
 * different things: a permission cannot make an unavailable capability work.
 */
export function CapabilitiesPanel({
  capabilities,
  policy,
  permissionsHref,
  commentsHref,
}: {
  capabilities: Record<string, unknown>;
  policy: Policy;
  permissionsHref: string;
  commentsHref: string;
}) {
  const { t } = useTranslation();
  const keys = Object.keys(capabilities);
  const available = keys.filter((k) => capabilities[k] === true).length;
  const groups = [
    ...CAPABILITY_GROUPS.map((g) => ({ ...g, keys: g.capabilities.filter((c) => c in capabilities) })),
    { key: "other" as const, icon: SettingsIcon, keys: keys.filter((k) => !KNOWN_CAPABILITIES.has(k)) },
  ].filter((g) => g.keys.length > 0);

  return (
    <Surface aria-labelledby="agent-capabilities-title" data-testid="agent-capabilities" className="gap-4 p-4 sm:p-5">
      <SectionTitle
        id="agent-capabilities-title"
        icon={<ShieldCheckIcon />}
        title={t("agent.capabilities")}
        meta={keys.length ? t("agent.capability.summary", { available, total: keys.length }) : undefined}
      />
      {groups.length === 0 ? (
        <p className="rounded-xl bg-surface-subtle px-3.5 py-3 text-metadata text-secondary">{t("agent.capability.none")}</p>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => {
            const Icon = group.icon;
            const on = group.keys.filter((k) => capabilities[k] === true).length;
            return (
              <div key={group.key} role="group" aria-labelledby={`cap-group-${group.key}`} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <Icon aria-hidden="true" className="shrink-0 text-sm text-action" />
                  <h3 id={`cap-group-${group.key}`} className="text-xs font-semibold tracking-wide text-secondary uppercase">
                    {t(`agent.capability.group.${group.key}`)}
                  </h3>
                  <span className="ml-auto text-xs text-secondary tabular-nums">
                    {t("agent.capability.groupCount", { available: on, total: group.keys.length })}
                  </span>
                </div>
                <ul className="flex flex-col divide-y divide-border/70 rounded-xl bg-surface-subtle/60 px-3">
                  {group.keys.map((key) => {
                    const ok = capabilities[key] === true;
                    const mode = combinedMode(actionsForCapability(key), policy);
                    const conflict = !ok && mode !== null && mode !== "off";
                    return (
                      <li key={key} data-testid={`capability-${key}`} className="flex min-w-0 flex-col gap-0.5 py-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className={`min-w-0 flex-1 text-body [overflow-wrap:anywhere] ${ok ? "font-medium text-primary" : "text-secondary"}`}>
                            {t(`agent.capability.label.${key}`, { defaultValue: capabilityLabel(key, t) })}
                          </span>
                          <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-px text-[11px] leading-5 font-semibold ${ok ? TONE_PILL.success : TONE_PILL.neutral}`}>
                            {ok ? <CheckIcon aria-hidden="true" /> : <XIcon aria-hidden="true" />}
                            {t(ok ? "agent.available" : "agent.unavailable")}
                          </span>
                        </div>
                        {mode !== null ? (
                          <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-secondary">
                            <span>{t("agent.capability.assistant")}</span>
                            <ModeChip mode={mode} />
                            {conflict ? <span className="font-medium text-attention">{t("agent.capability.conflict")}</span> : null}
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
                {group.key === "comments" ? (
                  <div className="-mt-0.5">
                    <QuietLink to={commentsHref}>{t("agent.openComments")}</QuietLink>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      <div className="flex flex-col gap-1 border-t border-border pt-3">
        <p className="text-xs text-secondary">{t("agent.capabilityHint")}</p>
        <div>
          <QuietLink to={permissionsHref}>{t("agent.capability.editPermissions")}</QuietLink>
        </div>
      </div>
    </Surface>
  );
}

const CALENDAR_ACTIONS = ["calendar.book", "calendar.reschedule", "calendar.cancel"] as const;

/** The workspace's calendar connection as it really is, plus the assistant's booking permissions. */
export function CalendarPanel({ policy, permissionsHref }: { policy: Policy; permissionsHref: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const connections = useCalendarConnections(workspace.id);
  const connection = (connections.data ?? []).find((c) => c.status !== "disconnected" && !c.disconnected_at);
  const status = connection?.status ?? "none";
  const manage = `/w/${workspace.id}/more/settings/connections#calendar`;
  const pill =
    status === "connected" ? TONE_PILL.success : status === "needs_reauth" ? TONE_PILL.danger : status === "degraded" ? TONE_PILL.attention : TONE_PILL.neutral;

  return (
    <Surface aria-labelledby="agent-calendar-title" data-testid="agent-calendar" className="gap-3 p-4 sm:p-5">
      <SectionTitle
        id="agent-calendar-title"
        icon={<CalendarIcon />}
        title={t("calendar.title")}
        meta={
          connections.isSuccess ? (
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <span className={`inline-flex items-center rounded-full px-2 text-[11px] leading-5 font-semibold ${pill}`}>
                {t(`agent.calendar.status.${status}`, { defaultValue: status })}
              </span>
              {connection?.is_simulated ? <SimulatedBadge compact /> : null}
            </span>
          ) : undefined
        }
      />
      {connections.isPending ? (
        <SkeletonRows label={t("common.loading")} rows={1} />
      ) : connections.error ? (
        <ErrorMessage error={connections.error} />
      ) : !connection ? (
        <>
          <p className="text-metadata text-secondary">{t("calendar.intro")}</p>
          <div>
            <Link
              to={manage}
              className={`inline-flex min-h-10 items-center gap-2 rounded-control bg-action px-4 text-body font-semibold text-on-action hover:bg-action-hover ${FOCUS}`}
            >
              <LinkIcon aria-hidden="true" />
              {t("calendar.connectGoogle")}
            </Link>
          </div>
        </>
      ) : (
        <>
          <div className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-surface-subtle/60 px-3 py-2.5">
            <p className="text-body font-medium text-primary [overflow-wrap:anywhere]">
              {connection.calendar_summary ?? connection.account_email ?? connection.calendar_id}
            </p>
            {connection.calendar_timezone ? (
              <p className="text-xs text-secondary">{connection.calendar_timezone}</p>
            ) : null}
          </div>
          {status === "needs_reauth" || status === "degraded" ? (
            <p className={`flex items-start gap-2 rounded-lg px-3 py-2 text-metadata ${status === "needs_reauth" ? "bg-danger-subtle text-danger" : "bg-attention-subtle text-attention"}`}>
              <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0" />
              {t(`agent.calendar.problem.${status}`)}
            </p>
          ) : null}
          <dl className="flex flex-col gap-1.5">
            {CALENDAR_ACTIONS.map((action) => (
              <div key={action} className="flex min-w-0 items-center justify-between gap-3 text-metadata">
                <dt className="min-w-0 text-secondary">{t(actionLabelKey(action))}</dt>
                <dd>
                  <ModeChip mode={combinedMode([action], policy) ?? "off"} />
                </dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap items-center gap-x-4">
            <QuietLink to={manage}>{status === "needs_reauth" ? t("calendar.reconnectGoogle") : t("agent.calendar.manage")}</QuietLink>
            <QuietLink to={permissionsHref}>{t("calendar.configurePermissions")}</QuietLink>
          </div>
        </>
      )}
    </Surface>
  );
}

/**
 * Who controls the account and how it connects. Changing controller is rare and consequential, so
 * it sits behind "Advanced settings" with an explicit confirmation; it is owner-only.
 */
export function ControlPanel({
  account,
  data,
  owner,
}: {
  account: SocialAccount;
  data: Schema<"AgentOverview">;
  owner: boolean;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const ws = workspace.id;
  const change = useChangeAgent(ws, account.id);
  const [confirm, setConfirm] = useState(false);
  const legacy = data.controller_mode === "legacy";
  const connectionTone =
    account.status === "connected" ? TONE_PILL.success : account.status === "degraded" ? TONE_PILL.attention : TONE_PILL.danger;

  return (
    <Surface aria-labelledby="agent-control-title" data-testid="agent-control" className="gap-3 p-4 sm:p-5">
      <SectionTitle id="agent-control-title" icon={<SettingsIcon />} title={t("agent.control.title")} />
      <dl className="flex flex-col gap-2 text-metadata">
        <div className="flex min-w-0 flex-col gap-0.5">
          <dt className="text-xs font-medium text-secondary">{t("agent.control.controller")}</dt>
          <dd className="text-primary">{t(`agent.controller.${data.controller_mode}`, { defaultValue: data.controller_mode })}</dd>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <dt className="text-xs font-medium text-secondary">{t("agent.control.connection")}</dt>
          <dd className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-2 text-[11px] leading-5 font-semibold ${connectionTone}`}>
              {t(`agent.connection.${account.status}`, { defaultValue: account.status })}
            </span>
            {account.is_simulated ? <SimulatedBadge compact /> : null}
          </dd>
        </div>
      </dl>
      <div>
        <QuietLink to={`/w/${ws}/more/settings/connections`}>{t("automation.manageConnection")}</QuietLink>
      </div>

      {owner && !legacy ? (
        <details className="group rounded-xl bg-surface-subtle/60 px-3 open:pb-3">
          <summary className={`flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-control text-metadata font-semibold text-primary ${FOCUS}`}>
            {t("core.advanced")}
            <ChevronRightIcon aria-hidden="true" className="transition-transform group-open:rotate-90" />
          </summary>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-secondary">{t("agent.control.legacyHint")}</p>
            {confirm ? null : (
              <div>
                <Button variant="secondary" disabled={change.isPending} onClick={() => setConfirm(true)}>
                  {t("agent.returnLegacy")}
                </Button>
              </div>
            )}
          </div>
        </details>
      ) : null}

      {confirm && !legacy ? (
        <div className="flex flex-col gap-3 rounded-xl bg-attention-subtle px-3.5 py-3">
          <p className="flex items-start gap-2 text-metadata text-primary">
            <AlertIcon aria-hidden="true" className="mt-0.5 shrink-0 text-attention" />
            <span>{t("agent.migrationWarning")}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              pending={change.isPending}
              onClick={() =>
                change.mutate(
                  { command: "activate", version: data.config_version, requestId: newRequestId(), mode: "legacy" },
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
    </Surface>
  );
}
