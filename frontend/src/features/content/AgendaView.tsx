import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon, ClockIcon, SpinnerIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ContentCard } from "./ContentCard";
import { useContentItems } from "./hooks";

interface DateGroup {
  dateKey: string;
  formattedDate: string;
  items: ContentItem[];
}

export function AgendaView() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const scheduled = useContentItems(workspace.id, "scheduled");

  if (scheduled.isPending) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-secondary">
        <SpinnerIcon className="motion-safe:animate-spin text-base text-action" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }
  if (scheduled.isError) return <ErrorMessage error={scheduled.error} />;

  const items = scheduled.data?.filter(
    (item) => item.status === "scheduled" || item.status === "publishing" || item.status === "retry_scheduled",
  ) ?? [];

  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState title={t("content.agendaEmpty")} description={t("content.agendaNotice")} />
      </div>
    );
  }

  // Group items by local date in workspace timezone
  const groupsMap = new Map<string, { formattedDate: string; items: ContentItem[] }>();

  for (const item of items) {
    const dateObj = item.scheduled_at ? new Date(item.scheduled_at) : new Date(item.updated_at);
    const dateKey = dateObj.toLocaleDateString("en-CA", { timeZone: workspace.timezone }); // YYYY-MM-DD
    const formattedDate = dateObj.toLocaleDateString(i18n.language, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: workspace.timezone,
    });

    if (!groupsMap.has(dateKey)) {
      groupsMap.set(dateKey, { formattedDate, items: [] });
    }
    groupsMap.get(dateKey)!.items.push(item);
  }

  const groups: DateGroup[] = Array.from(groupsMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dateKey, val]) => ({
      dateKey,
      formattedDate: val.formattedDate,
      items: val.items,
    }));

  return (
    <div className="flex flex-col gap-6" data-testid="agenda-view">
      {/* Timezone Notice Banner */}
      <div className="flex items-center justify-between text-xs text-secondary bg-surface-subtle rounded-control p-3.5 border border-border shadow-xs">
        <span className="flex items-center gap-1.5">
          <ClockIcon className="text-sm text-secondary" />
          <span>{t("content.agendaNotice")}</span>
        </span>
        <span className="font-semibold text-primary">{workspace.timezone}</span>
      </div>

      {/* Timeline grouped by day */}
      <div className="flex flex-col gap-8">
        {groups.map((group) => (
          <section key={group.dateKey} aria-labelledby={`date-heading-${group.dateKey}`} className="flex flex-col gap-3.5">
            <div className="flex items-center justify-between border-b border-border pb-2.5">
              <h2
                id={`date-heading-${group.dateKey}`}
                className="flex items-center gap-2 text-base font-bold text-primary"
              >
                <div className="flex items-center justify-center size-7 rounded-control bg-assistant text-action">
                  <CalendarIcon className="text-base" />
                </div>
                <span>{group.formattedDate}</span>
              </h2>
              <span className="rounded-full bg-surface-subtle border border-border px-2.5 py-0.5 text-xs font-semibold text-secondary">
                {group.items.length}
              </span>
            </div>
            <ul className="flex flex-col gap-3 pl-1 sm:pl-3 border-l-2 border-border/60">
              {group.items.map((item) => (
                <li key={item.id}>
                  <ContentCard item={item} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
