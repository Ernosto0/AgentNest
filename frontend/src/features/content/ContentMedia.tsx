import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { ImageIcon } from "@/components/icons";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useMediaPreview } from "./hooks";

type MediaItem = Pick<ContentItem, "media_asset_id" | "media_deleted">;

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
  const mediaId = item.media_deleted ? null : item.media_asset_id;
  const preview = useMediaPreview(workspace.id, mediaId);
  const [broken, setBroken] = useState<string | null>(null);

  const frame = `relative isolate overflow-hidden bg-surface-subtle ${className}`;

  if (preview.url && broken !== preview.url) {
    return (
      <div className={frame}>
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

  const label = item.media_deleted
    ? t("content.card.imageDeleted")
    : mediaId !== null
      ? t("content.card.imageFailed")
      : t("content.card.noImage");
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
