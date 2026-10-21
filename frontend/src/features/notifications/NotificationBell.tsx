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
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600"
    >
      <BellIcon className="text-2xl" />
      {unread > 0 ? (
        <span
          data-testid="notification-count"
          className="absolute top-1 right-1 min-w-5 rounded-full bg-red-700 px-1 text-center text-xs font-semibold text-white"
        >
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}
