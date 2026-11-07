import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ActivityEntry } from "@/api/types";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/Layout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, SparkIcon, UsersIcon } from "@/components/icons";
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
    <div className="flex flex-col gap-6 w-full">
      <PageHeader title={t("activity.title")} description={t("activity.intro")} />

      <div role="group" aria-label={t("activity.filterLabel")} className="flex flex-wrap gap-1.5 p-1 bg-surface-subtle/80 rounded-xl border border-border/70 shadow-2xs w-fit">
        {[null, ...ACTIVITY_GROUPS].map((name) => {
          const active = group === name;
          return (
            <button
              key={name ?? "all"}
              type="button"
              aria-pressed={active}
              onClick={() => choose(name)}
              className={`inline-flex min-h-11 items-center rounded-control px-3 py-2 text-body font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                active
                  ? "bg-surface text-primary shadow-xs font-bold ring-1 ring-border/50"
                  : "text-secondary hover:bg-surface/50 hover:text-primary"
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
        <div className="flex flex-col gap-5">
          {grouped.map((group) => (
            <div key={group.dayKey} className="grid min-w-0 gap-3 lg:grid-cols-[10rem_minmax(0,1fr)] lg:gap-6">
              <div className="pt-4 lg:sticky lg:top-24 lg:self-start">
                <h2 className="text-xs font-bold uppercase tracking-wider text-secondary">
                  {group.label}
                </h2>
              </div>
              <ul className="min-w-0 divide-y divide-border rounded-panel border border-border bg-surface" aria-label={group.label}>
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
        <div>
          <Button variant="secondary" disabled={feed.isFetchingNextPage} onClick={() => feed.fetchNextPage()}>
            {feed.isFetchingNextPage ? t("common.loading") : t("activity.loadMore")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function EntryRow({ entry, when }: { entry: ActivityEntry; when: string }) {
  const { t } = useTranslation();
  const { resource } = entry;
  const isAgent = entry.actor.type === "agent" || entry.actor.type === "system";

  return (
    <div className="flex items-start gap-3.5 p-4 transition-colors hover:bg-surface-subtle/40" data-testid="activity-entry">
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
          isAgent ? "bg-assistant text-action border border-action/20" : "bg-surface-subtle text-secondary border border-border"
        }`}
        aria-hidden="true"
      >
        {isAgent ? <SparkIcon className="text-base" /> : <UsersIcon className="text-base" />}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-heading font-semibold text-primary text-sm">{entry.text}</p>
          {entry.is_simulated ? <SimulatedBadge /> : null}
        </div>
        {resource ? (
          <p className="text-sm">
            {resource.link ? (
              <Link
                to={resource.link}
                className="font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              >
                {resource.label}
              </Link>
            ) : (
              <span className="text-secondary">{resource.label}</span>
            )}
          </p>
        ) : null}
        <div className="flex items-center gap-1.5 text-xs text-secondary mt-0.5">
          <ClockIcon className="text-xs shrink-0" />
          <p>{t("activity.byAt", { actor: entry.actor.label, time: when })}</p>
        </div>
      </div>
    </div>
  );
}
