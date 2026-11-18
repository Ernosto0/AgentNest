import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { ImageIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useMediaPreview } from "./hooks";
import { formatVideoTime } from "./reel";

type MediaItem = Pick<ContentItem, "media_asset_id" | "media_deleted"> &
  Partial<Pick<ContentItem, "media_items" | "content_type" | "cover_media_asset_id" | "cover_media_deleted" | "video_duration_ms">>;

/**
 * The item's stored image inside a fixed frame (the caller sets size and aspect). Any image ratio
 * is shown whole: it sits on a blurred, dimmed copy of itself, so a 9:16 story or a 1.91:1 post
 * keeps its shape in a uniform grid. Without an image the frame says so in words (no artwork that
 * could pass for uploaded media). `compact` drops the words for small thumbnails.
 */
export function ContentMedia({
  item,
  className = "",
  compact = false,
}: {
  item: MediaItem;
  className?: string;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const first = item.media_items?.[0];
  const isReel = item.content_type === "reel";
  const coverId = isReel && item.cover_media_asset_id && !item.cover_media_deleted ? item.cover_media_asset_id : null;
  const mediaId = first
    ? first.media_deleted
      ? null
      : first.media_asset_id
    : coverId ?? (item.media_deleted ? null : item.media_asset_id);
  const preview = useMediaPreview(workspace.id, mediaId);
  const [broken, setBroken] = useState<string | null>(null);

  const frame = `relative isolate overflow-hidden bg-surface-subtle ${className}`;
  const durationBadge =
    isReel && item.video_duration_ms !== null && item.video_duration_ms !== undefined
      ? formatVideoTime(item.video_duration_ms)
      : null;

  if (preview.url && broken !== preview.url) {
    return (
      <div className={frame}>
        {(item.media_items?.length ?? 0) > 0 ? <span className="absolute right-2 bottom-2 z-10 rounded bg-surface px-2 py-1 text-xs">{t("content.carousel.count", { count: item.media_items?.length })}</span> : null}
        {durationBadge ? (
          <span className="absolute right-2 bottom-2 z-10 rounded bg-surface/90 px-2 py-0.5 text-xs font-medium text-primary tabular-nums">
            {durationBadge}
          </span>
        ) : null}
        <img src={preview.url} alt="" aria-hidden="true" className="absolute inset-0 -z-10 size-full scale-110 object-cover opacity-60 blur-xl" />
        <img
          src={preview.url}
          alt=""
          onError={() => setBroken(preview.url)}
          className="size-full object-contain transition-transform duration-300 ease-out motion-safe:group-hover:scale-[1.02]"
        />
      </div>
    );
  }

  if (mediaId !== null && preview.isPending) {
    return (
      <div aria-hidden="true" className={`${frame} motion-safe:animate-pulse`} />
    );
  }

  const label = preview.kind === "video"
    ? `${t("content.media.videoPlaceholder")}${preview.durationMs ? ` · ${Math.ceil(preview.durationMs / 1000)} s` : ""}`
    : item.media_deleted
      ? t(isReel ? "content.card.videoDeleted" : "content.card.imageDeleted")
      : mediaId !== null
        ? t("content.card.imageFailed")
        : t(isReel ? "content.card.noVideo" : "content.card.noImage");
  return (
    <div
      className={`${frame} flex flex-col items-center justify-center gap-1.5 p-2 text-center ${
        item.media_deleted ? "bg-attention-subtle text-attention" : "text-secondary"
      }`}
      title={compact ? label : undefined}
    >
      {/* Faint grid: reads as "an empty frame", never as a picture. */}
      <span
        aria-hidden="true"
        className="absolute inset-0 -z-10 opacity-60 [background-image:linear-gradient(var(--an-border)_1px,transparent_1px),linear-gradient(90deg,var(--an-border)_1px,transparent_1px)] [background-size:16px_16px]"
      />
      <ImageIcon aria-hidden="true" className={compact ? "text-base opacity-70" : "text-2xl opacity-70"} />
      {compact ? <span className="sr-only">{label}</span> : <span className="text-xs font-medium">{label}</span>}
    </div>
  );
}
