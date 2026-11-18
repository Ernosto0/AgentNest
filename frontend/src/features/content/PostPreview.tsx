import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { ImageIcon, VideoIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useMediaPreview } from "./hooks";
import { mediaContentUrl } from "./reel";

export function PostPreview({ item, caption, overlay, account }: {
  item: ContentItem; caption: string; overlay: readonly string[]; account?: string;
}) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [position, setPosition] = useState(0);
  const images = item.media_items ?? [];
  const selected = images[Math.min(position, images.length - 1)];
  const deleted = selected?.media_deleted ?? item.media_deleted;
  const mediaId = selected?.media_asset_id ?? item.media_asset_id;
  const media = useMediaPreview(workspace.id, deleted ? null : mediaId);
  const coverId =
    item.content_type === "reel" && item.cover_media_asset_id && !item.cover_media_deleted
      ? item.cover_media_asset_id
      : null;
  const cover = useMediaPreview(workspace.id, coverId);
  const [failed, setFailed] = useState(false);
  const story = item.content_type === "story_image";
  const reel = item.content_type === "reel";
  return <section aria-label={t("core.preview")} className="flex min-w-0 flex-col gap-3" data-testid="post-preview">
    <h2 className="type-section">{t("core.preview")}</h2>
    <p className="text-metadata text-secondary">{t("core.approximate")}</p>
    <div className="overflow-hidden rounded-panel border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 p-4"><strong className="break-all">{account ? `@${account}` : t("core.noAccount")}</strong>{item.is_simulated ? <SimulatedBadge /> : null}</div>
      <div className={`flex items-center justify-center bg-surface-subtle ${story || reel ? "aspect-9/16 max-h-[60dvh]" : "aspect-square"}`}>
        {reel && mediaId && !deleted ? (
          <video
            controls
            playsInline
            preload="metadata"
            src={mediaContentUrl(workspace.id, mediaId)}
            poster={cover.url ?? media.url ?? undefined}
            aria-label={t("content.reel.previewLabel")}
            className="h-full w-full bg-black object-contain"
          />
        ) : media.url && !failed ? (
          <img src={media.url} onError={() => setFailed(true)} alt={t("core.postImage")} className="h-full w-full object-contain" />
        ) : (
          <div className="flex flex-col items-center gap-3 p-5 text-center text-secondary">
            {reel ? <VideoIcon className="text-3xl" /> : <ImageIcon className="text-3xl" />}
            <p>{deleted ? t(reel ? "content.reel.deleted" : "content.media.deleted") : failed || media.error ? t("content.media.previewFailed") : mediaId ? t("content.media.loadingPreview") : t("content.schedule.noMedia")}</p>
          </div>
        )}
      </div>
      {images.length > 0 ? <div className="flex items-center justify-center gap-3" aria-live="polite">
        <button type="button" className="min-h-11 min-w-11 focus-visible:outline-2 focus-visible:outline-focus" disabled={position === 0} aria-label={t("content.carousel.previous")} onClick={() => { setPosition((p) => Math.max(0, p - 1)); setFailed(false); }}>&larr;</button>
        <span>{Math.min(position + 1, images.length)} / {images.length}</span>
        <button type="button" className="min-h-11 min-w-11 focus-visible:outline-2 focus-visible:outline-focus" disabled={position >= images.length - 1} aria-label={t("content.carousel.next")} onClick={() => { setPosition((p) => Math.min(images.length - 1, p + 1)); setFailed(false); }}>&rarr;</button>
      </div> : null}
      {!story ? <p className="whitespace-pre-wrap break-words p-4 text-form">{caption || t("content.schedule.noCaption")}</p> : <div className="p-4"><p className="text-metadata text-secondary">{t("content.editor.overlayNote")}</p><ul className="mt-2 space-y-2">{overlay.filter(Boolean).map((line, index) => <li key={index} className="whitespace-pre-wrap break-words">{line}</li>)}</ul></div>}
    </div>
  </section>;
}
