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
        className="max-h-40 w-auto max-w-full rounded-lg object-contain ring-1 ring-slate-200"
      />
    );
  }
  return (
    <p className="text-sm text-slate-600" data-testid="preview-media">
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
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm" data-testid="content-preview">
      <dt className="text-slate-600">{t(labels.media)}</dt>
      <dd className="min-w-0">
        {mediaId && mediaDeleted ? (
          <span data-testid="preview-media-deleted">{t("content.media.deleted")}</span>
        ) : mediaId ? (
          <MediaThumb mediaId={mediaId} />
        ) : (
          t(labels.noMedia)
        )}
      </dd>
      {isStory ? (
        <>
          <dt className="text-slate-600">{t(labels.overlay)}</dt>
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
              t(labels.noCaption)
            )}
            <p className="mt-1 text-xs text-slate-600">{t(labels.overlayNote)}</p>
          </dd>
        </>
      ) : (
        <>
          <dt className="text-slate-600">{t(labels.caption)}</dt>
          <dd className="min-w-0 break-words whitespace-pre-wrap" data-testid="preview-caption">
            {caption && caption.trim() !== "" ? caption : t(labels.noCaption)}
          </dd>
        </>
      )}
    </dl>
  );
}
