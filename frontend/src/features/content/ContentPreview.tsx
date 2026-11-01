import { useTranslation } from "react-i18next";
import type { ContentType } from "@/api/types";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useMediaPreview } from "./hooks";

/** The stored image, small, fetched with the session (never a public URL). */
function MediaThumb({ mediaId }: { mediaId: string }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const preview = useMediaPreview(workspace.id, mediaId);
  if (preview.url) {
    return (
      <img
        src={preview.url}
        alt={t("content.media.previewAlt")}
        data-testid="preview-media"
        className="max-h-48 w-auto max-w-full rounded-control border border-border object-contain shadow-xs"
      />
    );
  }
  return (
    <p className="text-sm text-secondary" data-testid="preview-media">
      {preview.error ? t("content.media.previewFailed") : t("content.media.loadingPreview")}
    </p>
  );
}

interface ContentPreviewProps {
  contentType: ContentType;
  caption: string | null;
  overlay: readonly string[];
  mediaId: string | null;
  /** The image was deleted when its retention ended. */
  mediaDeleted?: boolean;
  /** i18n keys of the labels, so the schedule sheet and the approval sheet each keep their own wording. */
  labels: {
    media: string;
    caption: string;
    overlay: string;
    overlayNote: string;
    noMedia: string;
    noCaption: string;
  };
}

/**
 * Exactly the publishable parts of an item: the image, the caption (feed) or the overlay text
 * (story: written on the image, not published as text). Plain text, so nothing is interpreted.
 */
export function ContentPreview({
  contentType,
  caption,
  overlay,
  mediaId,
  mediaDeleted = false,
  labels,
}: ContentPreviewProps) {
  const { t } = useTranslation();
  const isStory = contentType === "story_image";
  const lines = overlay.filter((text) => text.trim() !== "");
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2.5 text-sm text-primary" data-testid="content-preview">
      <dt className="font-medium text-secondary">{t(labels.media)}</dt>
      <dd className="min-w-0">
        {mediaId && mediaDeleted ? (
          <span data-testid="preview-media-deleted" className="text-secondary">{t("content.media.deleted")}</span>
        ) : mediaId ? (
          <MediaThumb mediaId={mediaId} />
        ) : (
          <span className="text-secondary">{t(labels.noMedia)}</span>
        )}
      </dd>
      {isStory ? (
        <>
          <dt className="font-medium text-secondary">{t(labels.overlay)}</dt>
          <dd className="min-w-0">
            {lines.length > 0 ? (
              <ul className="list-disc pl-5">
                {lines.map((text, index) => (
                  <li key={index} data-testid="preview-overlay-item" className="break-words whitespace-pre-wrap">
                    {text}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-secondary">{t(labels.noCaption)}</span>
            )}
            <p className="mt-1 text-xs text-secondary">{t(labels.overlayNote)}</p>
          </dd>
        </>
      ) : (
        <>
          <dt className="font-medium text-secondary">{t(labels.caption)}</dt>
          <dd className="min-w-0 break-words whitespace-pre-wrap" data-testid="preview-caption">
            {caption && caption.trim() !== "" ? caption : <span className="text-secondary">{t(labels.noCaption)}</span>}
          </dd>
        </>
      )}
    </dl>
  );
}
