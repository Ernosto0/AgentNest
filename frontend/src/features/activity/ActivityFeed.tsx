import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ActivityEntry } from "@/api/types";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { shiftDay, todayIn } from "@/features/reports/dates";
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
  const entries = useMemo(() => feed.data?.pages.flatMap((page) => page.items) ?? [], [feed.data]);

  const choose = (next: ActivityGroup | null) =>
    setParams(next ? { type: next } : {}, { replace: true });

  // Times are shown on the workspace clock, not the phone's (INV-19).
  const when = (value: string) =>
    new Date(value).toLocaleString(i18n.language, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: workspace.timezone,
    });

  // Group entries by local date on the workspace clock
  const grouped = useMemo(() => {
    const groups: { dayKey: string; label: string; items: ActivityEntry[] }[] = [];
    const map = new Map<string, ActivityEntry[]>();
    for (const entry of entries) {
      const dayKey = todayIn(workspace.timezone, new Date(entry.occurred_at));
      let list = map.get(dayKey);
      if (!list) {
        list = [];
        map.set(dayKey, list);
        const today = todayIn(workspace.timezone);
        const yesterday = shiftDay(today, -1);
        let label: string;
        if (dayKey === today) {
          label = t("activity.today");
        } else if (dayKey === yesterday) {
          label = t("activity.yesterday");
        } else {
          label = new Date(`${dayKey}T12:00:00Z`).toLocaleDateString(i18n.language, {
            dateStyle: "full",
            timeZone: "UTC",
          });
        }
        groups.push({ dayKey, label, items: list });
      }
      list.push(entry);
    }
    return groups;
  }, [entries, workspace.timezone, i18n.language, t]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-heading font-semibold text-primary">{t("activity.title")}</h1>
        <p className="mt-1 text-sm text-secondary">{t("activity.intro")}</p>
      </div>

      <div role="group" aria-label={t("activity.filterLabel")} className="flex flex-wrap gap-2">
        {[null, ...ACTIVITY_GROUPS].map((name) => {
          const active = group === name;
          return (
            <button
              key={name ?? "all"}
              type="button"
              aria-pressed={active}
              onClick={() => choose(name)}
              className={`inline-flex min-h-11 items-center rounded-button px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-focus ${
                active
                  ? "bg-brand text-white shadow-xs"
                  : "border border-border bg-surface text-secondary hover:bg-surface-subtle hover:text-primary"
              }`}
            >
              {name ? t(`activity.groups.${name}`) : t("activity.groups.all")}
            </button>
          );
        })}
      </div>

      {feed.isError ? <ErrorMessage error={feed.error} /> : null}
      {feed.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {feed.data && entries.length === 0 ? (
        <EmptyState title={t("activity.empty")} description={t("activity.emptyHint")} />
      ) : null}
      {entries.length > 0 ? (
        <div className="flex flex-col gap-4">
          {grouped.map((group) => (
            <div key={group.dayKey} className="overflow-hidden rounded-panel border border-border bg-surface shadow-xs">
              <div className="border-b border-border bg-surface-subtle px-4 py-2">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-secondary">
                  {group.label}
                </h2>
              </div>
              <ul className="divide-y divide-border" aria-label={group.label}>
                {group.items.map((entry) => (
                  <li key={entry.id}>
                    <EntryRow entry={entry} when={when(entry.occurred_at)} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
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
    <div className="flex flex-col gap-1.5 p-4" data-testid="activity-entry">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-primary">{entry.text}</p>
        {entry.is_simulated ? <SimulatedBadge /> : null}
      </div>
      {resource ? (
        <p className="text-sm">
          {resource.link ? (
            <Link
              to={resource.link}
              className="font-medium text-brand hover:underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-focus"
            >
              {resource.label}
            </Link>
          ) : (
            <span className="text-secondary">{resource.label}</span>
          )}
        </p>
      ) : null}
      <p className="text-xs text-tertiary">
        {t("activity.byAt", { actor: entry.actor.label, time: when })}
      </p>
    </div>
  );
}
