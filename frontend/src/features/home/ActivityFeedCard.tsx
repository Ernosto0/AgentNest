import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card } from "@/components/Card";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SparkIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useRecentAgentActivity } from "./hooks";

export function ActivityFeedCard() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();

  // Activity view is for owners and managers only
  const enabled = role !== "staff";
  const activity = useRecentAgentActivity(workspace.id, enabled);

  if (!enabled) return null;

  const entries = activity.data ?? [];

  return (
    <Card className="flex flex-col gap-4 bg-surface p-5" data-testid="activity-feed-card">
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <SparkIcon className="text-action text-base" />
          <h2 className="type-section text-primary">{t("home.activity.title")}</h2>
        </div>
        <Link
          to={`/w/${workspace.id}/more/activity`}
          className="text-xs font-semibold text-action hover:underline"
        >
          {t("home.activity.all")}
        </Link>
      </div>

      {activity.error ? (
        <ErrorMessage error={activity.error} />
      ) : activity.isPending ? (
        <p className="text-body text-secondary">{t("common.loading")}</p>
      ) : entries.length === 0 ? (
        <p className="text-body text-secondary text-sm" data-testid="activity-empty">
          {t("home.activity.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-border/60">
          {entries.map((entry) => {
            const date = new Date(entry.occurred_at);
            const timeLabel = date.toLocaleTimeString(i18n.language, {
              hour: "2-digit",
              minute: "2-digit",
              timeZone: workspace.timezone,
            });

            return (
              <li key={entry.id} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-medium text-primary leading-snug">
                    {entry.resource?.link ? (
                      <Link to={entry.resource.link} className="hover:text-action underline-offset-2 hover:underline">
                        {entry.text}
                      </Link>
                    ) : (
                      entry.text
                    )}
                  </p>
                  <span className="text-[11px] text-secondary shrink-0 font-mono">
                    {timeLabel}
                  </span>
                </div>
                {entry.is_simulated ? (
                  <div>
                    <SimulatedBadge />
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
