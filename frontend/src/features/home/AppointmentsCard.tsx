import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon, InboxIcon } from "@/components/icons";
import { shiftDay, todayIn } from "@/features/reports/dates";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, Panel, PanelHeading, PanelLink, SkeletonRows } from "./DashboardPanel";
import { useAppointmentsInfo } from "./hooks";

/** Today's and tomorrow's bookings. Customer contact details never appear on Today. */
export function AppointmentsCard() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const info = useAppointmentsInfo(workspace.id, workspace.timezone);

  if (!info.isPending && !info.error && !info.hasConnectedCalendar) {
    if (role !== "owner") return null;
    return (
      <Panel aria-labelledby="home-appointments-title" data-testid="appointments-card-unconnected" className="py-3 sm:py-3.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-subtle text-base text-action">
            <CalendarIcon />
          </span>
          <div className="min-w-0 flex-1 basis-48">
            <h2 id="home-appointments-title" className="font-heading text-body font-semibold text-primary">
              {t("home.appointments.title")}
            </h2>
            <p className="text-xs text-secondary">{t("home.appointments.connectCalendar")}</p>
          </div>
          <PanelLink to={`/w/${workspace.id}/more/settings/connections`} className="ml-auto">
            {t("home.appointments.connect")}
          </PanelLink>
        </div>
      </Panel>
    );
  }

  const appointments = info.activeAppointments;
  const today = todayIn(workspace.timezone);
  const tomorrow = shiftDay(today, 1);

  return (
    <Panel aria-labelledby="home-appointments-title" data-testid="appointments-card" className="gap-3">
      <PanelHeading
        id="home-appointments-title"
        icon={<CalendarIcon />}
        title={t("home.appointments.title")}
        meta={!info.error && !info.isPending ? t("home.appointments.window") : undefined}
        action={
          !info.error && !info.isPending ? (
            <span className="rounded-full bg-surface-subtle px-2.5 py-0.5 text-metadata font-bold text-primary tabular-nums">
              {appointments.length}
            </span>
          ) : undefined
        }
      />

      {info.error ? (
        <ErrorMessage error={info.error} />
      ) : info.isPending ? (
        <SkeletonRows label={t("common.loading")} rows={2} />
      ) : appointments.length === 0 ? (
        <p className="text-body text-secondary" data-testid="appointments-empty">
          {t("home.appointments.empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {appointments.map((appt) => {
            const start = new Date(appt.start_at);
            const time = start.toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit", timeZone: workspace.timezone });
            const day = todayIn(workspace.timezone, start);
            const dayText = day === today ? t("home.week.today") : day === tomorrow ? t("home.week.tomorrow") : "";
            return (
              <li key={appt.id} className="flex min-w-0 items-start gap-3 rounded-xl bg-surface-subtle/70 p-3">
                <div className="flex min-w-14 shrink-0 flex-col items-center rounded-lg bg-surface px-2 py-1.5 text-center whitespace-nowrap">
                  <span className="font-heading text-sm font-bold text-primary tabular-nums">{time}</span>
                  {dayText ? <span className="text-[0.6875rem] font-medium text-secondary">{dayText}</span> : null}
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-semibold text-primary">{appt.customer_name || appt.title}</span>
                  {appt.customer_name && appt.title !== appt.customer_name ? (
                    <span className="truncate text-metadata text-secondary">{appt.title}</span>
                  ) : null}
                  {appt.conversation_id ? (
                    <Link
                      to={`/w/${workspace.id}/inbox/${appt.conversation_id}`}
                      className={`mt-0.5 inline-flex min-h-8 w-fit items-center gap-1 rounded-control text-metadata font-semibold text-action hover:underline underline-offset-4 ${FOCUS}`}
                    >
                      <InboxIcon aria-hidden="true" />
                      <span>{t("home.appointments.viewConversation")}</span>
                    </Link>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
