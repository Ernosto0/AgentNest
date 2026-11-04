import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { BellIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useNotifications } from "./hooks";

/** The bell with the unread count; it opens the notification centre. */
export function NotificationBell() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const notifications = useNotifications(workspace.id);
  const unread = notifications.data?.unread_count ?? 0;

  return (
    <Link
      to={`/w/${workspace.id}/more/notifications`}
      // The badge reads "9+" from ten up; the accessible name must contain the visible text (WCAG 2.5.3).
      aria-label={`${t("notifications.bell")}${unread ? `, ${t("notifications.unread", { count: unread })}${unread > 9 ? " 9+" : ""}` : ""}`}
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl border border-border/70 bg-surface-subtle/60 text-secondary hover:bg-surface-subtle hover:text-primary hover:border-border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus transition-all shadow-2xs"
    >
      <BellIcon className="text-xl" />
      {unread > 0 ? (
        <span
          data-testid="notification-count"
          className="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger px-1 text-center text-[11px] font-bold text-white shadow-xs"
        >
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}
