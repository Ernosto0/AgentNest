import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { ChevronRightIcon } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { isGenerating } from "./hooks";
import { contentBadge } from "./status";

/** When the item goes out, went out, or last changed: whichever the status makes meaningful. */
function whenLine(
  item: ContentItem,
  t: ReturnType<typeof useTranslation>["t"],
  language: string,
  timezone: string,
): string | null {
  const format = (value: string) =>
    new Date(value).toLocaleString(language, { dateStyle: "short", timeStyle: "short", timeZone: timezone });
  if (item.status === "published" && item.published_at) {
    return t("content.card.publishedAt", { time: format(item.published_at) });
  }
  if (item.status === "scheduled" || item.status === "publishing" || item.status === "retry_scheduled") {
    return item.scheduled_at ? t("content.card.scheduledFor", { time: format(item.scheduled_at) }) : null;
  }
  return t("content.card.updatedAt", { time: format(item.updated_at) });
}

/** One row of the content list. The badge is the only statement of where the item stands (INV-18). */
export function ContentCard({ item }: { item: ContentItem }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const badge = contentBadge(item, t, i18n.language, workspace.timezone);
  const when = whenLine(item, t, i18n.language, workspace.timezone);

  return (
    <Link
      to={`/w/${workspace.id}/content/${item.id}`}
      data-content-id={item.id}
      data-testid="content-card"
      className="flex min-h-16 items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 ring-1 ring-slate-200 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
    >
      <span className="min-w-0">
        <span className="block truncate font-medium">{item.title || t("content.card.untitled")}</span>
        <span className="mt-0.5 block text-sm text-slate-600">
          {t(`content.type.${item.content_type}`)}
          {when ? ` · ${when}` : ""}
        </span>
        <span className="mt-1.5 flex flex-wrap items-center gap-2">
          <StatusBadge status={badge.status} params={badge.params} simulated={item.is_simulated} />
          {isGenerating(item) ? (
            <span className="text-sm text-slate-600" data-testid="card-generating">
              {t("content.card.generating")}
            </span>
          ) : null}
        </span>
      </span>
      <ChevronRightIcon className="shrink-0 text-xl text-slate-400" />
    </Link>
  );
}
