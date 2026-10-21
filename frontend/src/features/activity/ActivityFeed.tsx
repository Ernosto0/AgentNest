import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ActivityEntry } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ACTIVITY_GROUPS, isActivityGroup, useActivity, type ActivityGroup } from "./hooks";

/** What happened in the workspace, newest first: the audit log in plain language (J5). */
export function ActivityFeed() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();
  const requested = params.get("type");
  const group: ActivityGroup | null = isActivityGroup(requested) ? requested : null;
  const feed = useActivity(workspace.id, group);
  const entries = feed.data?.pages.flatMap((page) => page.items) ?? [];

  const choose = (next: ActivityGroup | null) =>
    setParams(next ? { type: next } : {}, { replace: true });

  // Times are shown on the workspace clock, not the phone's (INV-19).
  const when = (value: string) =>
    new Date(value).toLocaleString(i18n.language, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: workspace.timezone,
    });

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("activity.title")}</h1>
        <p className="mt-1 text-slate-600">{t("activity.intro")}</p>
      </div>

      <div role="group" aria-label={t("activity.filterLabel")} className="flex flex-wrap gap-2">
        {[null, ...ACTIVITY_GROUPS].map((name) => (
          <button
            key={name ?? "all"}
            type="button"
            aria-pressed={group === name}
            onClick={() => choose(name)}
            className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              group === name ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
            }`}
          >
            {name ? t(`activity.groups.${name}`) : t("activity.groups.all")}
          </button>
        ))}
      </div>

      {feed.isError ? <ErrorMessage error={feed.error} /> : null}
      {feed.isPending ? <p>{t("common.loading")}</p> : null}
      {feed.data && entries.length === 0 ? (
        <EmptyState title={t("activity.empty")} description={t("activity.emptyHint")} />
      ) : null}
      {entries.length > 0 ? (
        <Card className="p-0">
          <ul className="divide-y divide-slate-200" aria-label={t("activity.title")}>
            {entries.map((entry) => (
              <li key={entry.id}>
                <EntryRow entry={entry} when={when(entry.occurred_at)} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {feed.hasNextPage ? (
        <Button variant="secondary" disabled={feed.isFetchingNextPage} onClick={() => feed.fetchNextPage()}>
          {feed.isFetchingNextPage ? t("common.loading") : t("activity.loadMore")}
        </Button>
      ) : null}
    </div>
  );
}

function EntryRow({ entry, when }: { entry: ActivityEntry; when: string }) {
  const { t } = useTranslation();
  const { resource } = entry;
  return (
    <div className="flex flex-col gap-1 p-4" data-testid="activity-entry">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-slate-900">{entry.text}</p>
        {entry.is_simulated ? <SimulatedBadge /> : null}
      </div>
      {resource ? (
        <p className="text-sm">
          {resource.link ? (
            <Link
              to={resource.link}
              className="font-medium text-indigo-700 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600"
            >
              {resource.label}
            </Link>
          ) : (
            <span className="text-slate-700">{resource.label}</span>
          )}
        </p>
      ) : null}
      <p className="text-xs text-slate-600">
        {t("activity.byAt", { actor: entry.actor.label, time: when })}
      </p>
    </div>
  );
}
