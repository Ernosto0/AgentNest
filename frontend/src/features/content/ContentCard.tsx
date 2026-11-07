import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { ContentItem } from "@/api/types";
import { ChevronRightIcon, ImageIcon, SpinnerIcon } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { isGenerating, useMediaPreview } from "./hooks";
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

function ContentThumbnail({
  workspaceId,
  mediaId,
  deleted,
  contentType,
}: {
  workspaceId: string;
  mediaId: string | null;
  deleted?: boolean;
  contentType: string;
}) {
  const { t } = useTranslation();
  const preview = useMediaPreview(workspaceId, deleted ? null : mediaId);
  const aspectClass = contentType === "story_image" ? "aspect-9/16 w-20 sm:w-24" : "aspect-square w-24 sm:w-28";

  if (deleted) {
    return (
      <div
        className={`${aspectClass} flex shrink-0 items-center justify-center rounded-control bg-attention-subtle text-attention border border-attention/30 text-xs text-center p-1`}
        title={t("content.media.deleted")}
        aria-hidden="true"
      >
        <ImageIcon className="text-xl opacity-75" />
      </div>
    );
  }

  if (mediaId && preview.url) {
    return (
      <img
        src={preview.url}
        alt=""
        className={`${aspectClass} shrink-0 rounded-control object-cover border border-border shadow-xs`}
      />
    );
  }

  return (
    <div
      className={`${aspectClass} flex shrink-0 items-center justify-center rounded-control bg-surface-subtle text-secondary/60 border border-border`}
      aria-hidden="true"
    >
      <ImageIcon className="text-2xl" />
    </div>
  );
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
      className="group flex min-h-20 items-center justify-between gap-4 bg-surface p-4 sm:px-5 transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
    >
      <div className="flex items-center gap-3.5 min-w-0">
        <ContentThumbnail
          workspaceId={workspace.id}
          mediaId={item.media_asset_id}
          deleted={item.media_deleted}
          contentType={item.content_type}
        />
        <div className="flex flex-col min-w-0">
          <span className="truncate font-semibold text-primary text-base">{item.title || t("content.card.untitled")}</span>
          <span className="mt-0.5 block text-xs sm:text-sm text-secondary truncate">
            {t(`content.type.${item.content_type}`)}
            {when ? ` · ${when}` : ""}
          </span>
          <span className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={badge.status} params={badge.params} simulated={item.is_simulated} />
            {isGenerating(item) ? (
              <span
                className="inline-flex items-center gap-1.5 rounded-full bg-info-subtle px-2 py-0.5 text-xs font-medium text-info"
                data-testid="card-generating"
              >
                <SpinnerIcon className="size-3 motion-safe:animate-spin" />
                <span>{t("content.card.generating")}</span>
              </span>
            ) : null}
          </span>
        </div>
      </div>
      <ChevronRightIcon className="shrink-0 text-xl text-secondary/40 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
    </Link>
  );
}
