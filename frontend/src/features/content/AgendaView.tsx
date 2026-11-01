import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { CalendarIcon } from "@/components/icons";
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

  if (scheduled.isPending) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
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
      <div className="flex items-center justify-between text-xs text-slate-500 bg-slate-50 rounded-lg p-3 ring-1 ring-slate-200/60">
        <span>{t("content.agendaNotice")}</span>
        <span className="font-medium">{workspace.timezone}</span>
      </div>

      <div className="flex flex-col gap-6">
        {groups.map((group) => (
          <section key={group.dateKey} aria-labelledby={`date-heading-${group.dateKey}`} className="flex flex-col gap-3">
            <h2
              id={`date-heading-${group.dateKey}`}
              className="flex items-center gap-2 text-base font-bold text-slate-800 border-b border-slate-200 pb-2"
            >
              <CalendarIcon className="text-indigo-600 text-lg" />
              <span>{group.formattedDate}</span>
            </h2>
            <ul className="flex flex-col gap-3">
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
