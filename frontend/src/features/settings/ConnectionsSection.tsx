import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertIcon, CalendarIcon, ChatIcon, CheckIcon, ChevronRightIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useSocialAccounts } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useCalendarConnections } from "./hooks";
import { FOCUS, LINK_BUTTON, SettingsPanel, SettingsSection } from "./SettingsParts";

type Status = "connected" | "degraded" | "needs_reauth" | "disconnected" | "none";

const PILL: Record<Status, string> = {
  connected: "bg-success-subtle text-success",
  degraded: "bg-attention-subtle text-attention",
  needs_reauth: "bg-danger-subtle text-danger",
  disconnected: "bg-surface-subtle text-secondary",
  none: "bg-surface-subtle text-secondary",
};

function asStatus(value: string | undefined): Status {
  return value === "connected" || value === "degraded" || value === "needs_reauth" || value === "disconnected" ? value : "none";
}

/** The connection state in words; colour and icon only reinforce it. */
function ConnectionPill({ status }: { status: Status }) {
  const { t } = useTranslation();
  const Icon = status === "connected" ? CheckIcon : status === "degraded" || status === "needs_reauth" ? AlertIcon : null;
  return (
    <span data-status={status} className={`inline-flex items-center gap-1 rounded-full px-2 py-px text-xs leading-5 font-semibold ${PILL[status]}`}>
      {Icon ? <Icon aria-hidden="true" className="text-[0.8125rem]" /> : null}
      {t(`settings.connections.status.${status}`)}
    </span>
  );
}

function ConnectionRow({
  icon,
  service,
  detail,
  status,
  simulated,
  problem,
  action,
  loading,
  failed,
}: {
  icon: ReactNode;
  service: string;
  detail?: ReactNode;
  status?: Status;
  simulated?: boolean;
  problem?: string;
  action: ReactNode;
  loading: boolean;
  failed: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-3 border-t border-border/70 px-4 py-4 first:border-t-0 sm:flex-nowrap sm:px-5">
      <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface-subtle text-lg text-action">
        {icon}
      </span>
      <div className="min-w-0 flex-1 basis-48">
        <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-body font-semibold text-primary">{service}</span>
          {loading ? (
            <span className="h-5 w-24 rounded-full bg-surface-subtle motion-safe:animate-pulse" aria-hidden="true" />
          ) : status ? (
            <ConnectionPill status={status} />
          ) : null}
          {simulated ? <SimulatedBadge compact /> : null}
        </p>
        {loading ? (
          <span className="sr-only">{t("common.loading")}</span>
        ) : failed ? (
          <p className="text-metadata text-danger">{t("settings.connections.loadFailed")}</p>
        ) : (
          <>
            {detail ? <p className="text-metadata text-secondary [overflow-wrap:anywhere]">{detail}</p> : null}
            {problem ? <p className="mt-0.5 text-metadata font-medium text-attention">{problem}</p> : null}
          </>
        )}
      </div>
      <div className="ml-[3.25rem] sm:ml-0">{action}</div>
    </div>
  );
}

export function ConnectionsSection() {
  const { t } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const accounts = useSocialAccounts(workspace.id);
  const calendars = useCalendarConnections(workspace.id);
  const canManage = role === "owner"; // integrations.manage
  const page = `/w/${workspace.id}/more/settings/connections`;

  // A live account wins over a disconnected one; the list is the workspace's own accounts.
  const allAccounts = accounts.data ?? [];
  const account = allAccounts.find((a) => a.status !== "disconnected") ?? allAccounts[0];
  const igStatus: Status = account ? asStatus(account.status) : "none";
  const igAction = !canManage
    ? t("settings.connections.view")
    : igStatus === "none" || igStatus === "disconnected"
      ? t("settings.connections.connect")
      : igStatus === "needs_reauth"
        ? t("settings.connections.reconnect")
        : t("settings.connections.manage");

  const calendar = (calendars.data ?? []).find((c) => c.status !== "disconnected" && !c.disconnected_at);
  const calStatus: Status = calendar ? asStatus(calendar.status) : "none";
  const calAction = !canManage
    ? t("settings.connections.view")
    : calStatus === "none"
      ? t("settings.connections.connect")
      : calStatus === "needs_reauth"
        ? t("settings.connections.reconnect")
        : t("settings.connections.manage");

  const actionLink = (to: string, label: string, subject: string) => (
    <Link to={to} className={LINK_BUTTON} aria-label={t("settings.connections.actionLabel", { action: label, service: subject })}>
      {label}
    </Link>
  );

  return (
    <SettingsSection id="connections" title={t("settings.nav.connections")} description={t("settings.connections.description")}>
      <SettingsPanel>
        <ConnectionRow
          icon={<ChatIcon />}
          service="Instagram"
          loading={accounts.isPending}
          failed={accounts.isError}
          status={igStatus}
          simulated={account?.is_simulated}
          detail={
            account && igStatus !== "disconnected"
              ? account.username
                ? `@${account.username}`
                : t("settings.connections.instagramAccount")
              : t("settings.connections.instagramNone")
          }
          problem={
            igStatus === "needs_reauth"
              ? t("settings.connections.instagramReauth")
              : igStatus === "degraded"
                ? t("settings.connections.instagramDegraded")
                : undefined
          }
          action={actionLink(page, igAction, "Instagram")}
        />
        <ConnectionRow
          icon={<CalendarIcon />}
          service="Google Calendar"
          loading={calendars.isPending}
          failed={calendars.isError}
          status={calStatus}
          simulated={calendar?.is_simulated}
          detail={calendar ? calendar.account_email ?? calendar.calendar_summary ?? undefined : t("settings.connections.calendarNone")}
          problem={calStatus === "needs_reauth" || calStatus === "degraded" ? t(`agent.calendar.problem.${calStatus}`) : undefined}
          action={actionLink(`${page}#calendar`, calAction, "Google Calendar")}
        />
        <Link
          to={page}
          className={`group flex min-h-12 items-center justify-between gap-3 rounded-b-2xl border-t border-border/70 px-4 py-3 text-body font-medium text-action hover:bg-surface-subtle/60 sm:px-5 ${FOCUS} focus-visible:-outline-offset-2`}
        >
          <span>{t("settings.connections.all")}</span>
          <ChevronRightIcon aria-hidden="true" className="shrink-0 text-lg transition-transform duration-150 group-hover:translate-x-0.5 motion-reduce:transition-none" />
        </Link>
      </SettingsPanel>
    </SettingsSection>
  );
}
