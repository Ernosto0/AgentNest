import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { AppNotification } from "@/api/types";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { BellIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeNotification } from "./describe";
import { useMarkAllRead, useMarkRead, useNotifications } from "./hooks";

function target(workspaceId: string, notification: AppNotification): string | null {
  if (notification.type.startsWith("approval.")) return `/w/${workspaceId}/approvals`;
  if (notification.type === "knowledge.fact_changed") return `/w/${workspaceId}/more/knowledge`;
  return null;
}

export function NotificationBell() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const notifications = useNotifications(workspace.id);
  const markRead = useMarkRead(workspace.id);
  const markAll = useMarkAllRead(workspace.id);
  const [open, setOpen] = useState(false);

  const unread = notifications.data?.unread_count ?? 0;
  const items = notifications.data?.items ?? [];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`${t("notifications.bell")}${unread ? `, ${t("notifications.unread", { count: unread })}` : ""}`}
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
      </button>
      {open ? (
        <BottomSheet
          title={t("notifications.title")}
          onClose={() => setOpen(false)}
          footer={
            unread > 0 ? (
              <Button variant="secondary" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
                {t("notifications.markAll")}
              </Button>
            ) : null
          }
        >
          {notifications.isError ? <ErrorMessage error={notifications.error} /> : null}
          {items.length === 0 ? <p className="text-slate-700">{t("notifications.empty")}</p> : null}
          <ul className="flex flex-col gap-3">
            {items.map((item) => {
              const to = target(workspace.id, item);
              return (
                <li
                  key={item.id}
                  data-unread={item.read_at === null}
                  className={`rounded-lg p-3 ring-1 ring-slate-200 ${item.read_at === null ? "bg-indigo-50" : "bg-white"}`}
                >
                  <p className="break-words">{describeNotification(t, item, i18n.language)}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                    <span className="text-slate-600">
                      {new Date(item.created_at).toLocaleString(i18n.language, {
                        dateStyle: "short",
                        timeStyle: "short",
                        timeZone: workspace.timezone,
                      })}
                    </span>
                    {item.is_simulated ? <SimulatedBadge /> : null}
                    {to ? (
                      <Link
                        to={to}
                        onClick={() => {
                          markRead.mutate(item.id);
                          setOpen(false);
                        }}
                        className="inline-flex min-h-11 items-center text-indigo-800 underline"
                      >
                        {t("notifications.open")}
                      </Link>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </BottomSheet>
      ) : null}
    </>
  );
}
