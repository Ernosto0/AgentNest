import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { AppNotification } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, CriticalIcon, InfoIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { describeNotification } from "./describe";
import { useMarkAllRead, useMarkRead, useNotifications } from "./hooks";
import { notificationTarget } from "./target";

const SEVERITY = {
  info: { Icon: InfoIcon, tone: "text-slate-700" },
  attention: { Icon: AlertIcon, tone: "text-amber-800" },
  critical: { Icon: CriticalIcon, tone: "text-red-800" },
} as const;

function severityOf(value: string): keyof typeof SEVERITY {
  return value === "attention" || value === "critical" ? value : "info";
}

/** Every notification of the signed-in person, unread first by default (user-journeys §1, J6). */
export function NotificationCenter() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [unreadOnly, setUnreadOnly] = useState(true);
  const list = useNotifications(workspace.id, unreadOnly);
  const all = useNotifications(workspace.id);
  const markRead = useMarkRead(workspace.id);
  const markAll = useMarkAllRead(workspace.id);

  // The bell and this screen share the unread count of the "all" list.
  const unread = all.data?.unread_count ?? list.data?.unread_count ?? 0;
  const items = list.data?.items ?? [];

  // A notification is read when its link is followed, not when the screen is opened.
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("notifications.title")}</h1>
        <p className="mt-1 text-slate-600">{t("notifications.intro")}</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label={t("notifications.filterLabel")} className="flex gap-2">
          {[true, false].map((only) => (
            <button
              key={String(only)}
              type="button"
              aria-pressed={unreadOnly === only}
              onClick={() => setUnreadOnly(only)}
              className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                unreadOnly === only ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
              }`}
            >
              {only ? t("notifications.filterUnread") : t("notifications.filterAll")}
            </button>
          ))}
        </div>
        {unread > 0 ? (
          <Button variant="secondary" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
            {t("notifications.markAll")}
          </Button>
        ) : null}
      </div>

      {list.isError ? <ErrorMessage error={list.error} /> : null}
      {markAll.isError ? <ErrorMessage error={markAll.error} /> : null}
      {list.isPending ? <p>{t("common.loading")}</p> : null}
      {list.data && items.length === 0 ? (
        <EmptyState
          title={unreadOnly ? t("notifications.empty") : t("notifications.emptyAll")}
          description={t("notifications.emptyHint")}
        />
      ) : null}
      {items.length > 0 ? (
        <Card className="p-0">
          <ul className="divide-y divide-slate-200" aria-label={t("notifications.title")}>
            {items.map((item) => (
              <li key={item.id}>
                <Row
                  item={item}
                  workspaceId={workspace.id}
                  onFollow={() => (item.read_at === null ? markRead.mutate(item.id) : undefined)}
                />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function Row({
  item,
  workspaceId,
  onFollow,
}: {
  item: AppNotification;
  workspaceId: string;
  onFollow: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const to = notificationTarget(workspaceId, item);
  const severity = severityOf(item.severity);
  const { Icon, tone } = SEVERITY[severity];
  return (
    <div
      data-unread={item.read_at === null}
      data-severity={severity}
      className={`flex flex-col gap-2 p-4 ${item.read_at === null ? "bg-indigo-50" : "bg-white"}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`inline-flex items-center gap-1 font-semibold ${tone}`}>
          <Icon className="text-lg" />
          {t(`notifications.severity.${severity}`)}
        </span>
        {item.read_at === null ? (
          <span className="rounded-full bg-indigo-700 px-2 py-0.5 text-xs font-semibold text-white">
            {t("notifications.unreadBadge")}
          </span>
        ) : null}
        {item.is_simulated ? <SimulatedBadge /> : null}
      </div>
      <p className="break-words">{describeNotification(t, item, i18n.language)}</p>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-600">
          {new Date(item.created_at).toLocaleString(i18n.language, {
            dateStyle: "short",
            timeStyle: "short",
            timeZone: workspace.timezone,
          })}
        </span>
        {to ? (
          <Link
            to={to}
            onClick={onFollow}
            className="inline-flex min-h-11 items-center font-medium text-indigo-800 underline"
          >
            {t("notifications.open")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
