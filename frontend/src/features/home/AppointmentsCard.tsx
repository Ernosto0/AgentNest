import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon, ClockIcon, LinkIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useAppointmentsInfo } from "./hooks";

export function AppointmentsCard() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const info = useAppointmentsInfo(workspace.id, workspace.timezone);

  // If no calendar connected
  if (!info.isPending && !info.error && !info.hasConnectedCalendar) {
    if (role !== "owner") return null;

    return (
      <Card className="flex flex-col gap-3 bg-surface p-5" data-testid="appointments-card-unconnected">
        <div className="flex items-center gap-2 text-primary font-semibold">
          <CalendarIcon className="text-action" />
          <h2>{t("home.appointments.title")}</h2>
        </div>
        <p className="text-body text-secondary text-sm">
          {t("home.appointments.connectCalendar")}
        </p>
        <div>
          <Link
            to={`/w/${workspace.id}/more/settings/connections`}
            className="inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover"
          >
            {t("common.settings")}
          </Link>
        </div>
      </Card>
    );
  }

  const appointments = info.activeAppointments;

  return (
    <Card className="flex flex-col gap-4 bg-surface p-5" data-testid="appointments-card">
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <CalendarIcon className="text-action text-base" />
          <h2 className="type-section text-primary">{t("home.appointments.title")}</h2>
        </div>
        {!info.error && !info.isPending ? <span className="text-xs font-semibold text-secondary font-mono">
          {appointments.length}
        </span> : null}
      </div>

      {info.error ? (
        <ErrorMessage error={info.error} />
      ) : info.isPending ? (
        <p className="text-body text-secondary">{t("common.loading")}</p>
      ) : appointments.length === 0 ? (
        <p className="text-body text-secondary text-sm" data-testid="appointments-empty">
          {t("home.appointments.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-border/60">
          {appointments.map((appt) => {
            const date = new Date(appt.start_at);
            const timeStr = date.toLocaleTimeString(i18n.language, {
              hour: "2-digit",
              minute: "2-digit",
              timeZone: workspace.timezone,
            });

            return (
              <li key={appt.id} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm text-primary">
                    {appt.customer_name || appt.title}
                  </span>
                  <span className="flex items-center gap-1 text-xs font-mono font-medium text-action bg-action-subtle/30 px-2 py-0.5 rounded-full">
                    <ClockIcon className="text-xs" />
                    {timeStr}
                  </span>
                </div>

                {appt.customer_name && appt.title !== appt.customer_name ? (
                  <p className="text-xs text-secondary truncate">{appt.title}</p>
                ) : null}

                {appt.conversation_id ? (
                  <div className="pt-0.5">
                    <Link
                      to={`/w/${workspace.id}/inbox/${appt.conversation_id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-action hover:underline"
                    >
                      <LinkIcon className="text-xs" />
                      <span>{t("home.appointments.viewConversation")}</span>
                    </Link>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
