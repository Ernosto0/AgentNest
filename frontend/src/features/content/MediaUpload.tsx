import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { AppError } from "@/api/errors";
import type { ContentCheckItem, ContentType, MediaAsset } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
import { AlertIcon, ImageIcon, SpinnerIcon } from "@/components/icons";
import { useMediaPreview, useUploadMedia } from "./hooks";
import { checkMessage } from "./messages";

const MB = 1024 * 1024;

/** Upload failures with a precise cause get their own sentence; anything else the shared catalog. */
function UploadError({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (error instanceof AppError) {
    if (error.code === "MEDIA_TOO_LARGE" && typeof error.params.limit_bytes === "number") {
      const limit = `${Math.max(1, Math.round(error.params.limit_bytes / MB))} MB`;
      return (
        <p role="alert" className="rounded-control border border-danger bg-danger-subtle p-3 text-sm text-danger shadow-xs">
          {t("content.media.tooLarge", { limit })}
        </p>
      );
    }
    const reason = typeof error.params.reason === "string" ? error.params.reason : null;
    if (error.code === "MEDIA_INVALID" && reason && ["EMPTY_FILE", "NOT_AN_IMAGE", "CORRUPT_IMAGE", "TOO_MANY_PIXELS"].includes(reason)) {
      return (
        <p role="alert" className="rounded-control border border-danger bg-danger-subtle p-3 text-sm text-danger shadow-xs">
          {t(`content.media.reason.${reason}`)}
        </p>
      );
    }
  }
  return <ErrorMessage error={error} />;
}

interface MediaUploadProps {
  workspaceId: string;
  contentType: ContentType;
  /** The image attached to the item now, if any. */
  mediaId: string | null;
  /** The image was deleted when its retention ended: say so instead of fetching a missing file. */
  deleted?: boolean;
  /** Called with the stored asset once the upload succeeded; the parent attaches it to the item. */
  onUploaded: (asset: MediaAsset) => void;
  /** Warnings about the image (for instance a story that is not 9:16). */
  warnings?: ContentCheckItem[];
  disabled?: boolean;
}

/** Pick or take a photo, send it, and see it back. The preview is fetched with the session (never a public URL). */
export function MediaUpload({
  workspaceId,
  contentType,
  mediaId,
  deleted = false,
  onUploaded,
  warnings = [],
  disabled = false,
}: MediaUploadProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const upload = useUploadMedia(workspaceId);
  const preview = useMediaPreview(workspaceId, deleted ? null : mediaId);
  const [asset, setAsset] = useState<MediaAsset | null>(null);
  const shown = asset !== null && asset.id === mediaId ? asset : null;

  const choose = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (stored) => {
        setAsset(stored);
        onUploaded(stored);
      },
    });
  };

  return (
    <div className="flex flex-col gap-3" data-testid="media-upload">
      <div>
        <span className="text-sm font-semibold text-primary">{t("content.media.label")}</span>
        <p className="mt-0.5 text-xs text-secondary">
          {contentType === "story_image" ? t("content.media.storyHint") : t("content.media.feedHint")}
        </p>
      </div>

      {mediaId && deleted ? (
        <p
          className="rounded-control border border-attention bg-attention-subtle p-4 text-sm text-attention shadow-xs"
          data-testid="media-deleted"
        >
          {t("content.media.deleted")}
        </p>
      ) : mediaId ? (
        <div className="overflow-hidden rounded-panel border border-border bg-surface-subtle p-2 shadow-xs">
          {preview.url ? (
            <div className="flex flex-col items-center gap-2">
              <img
                src={preview.url}
                alt={t("content.media.previewAlt")}
                className="max-h-80 w-auto max-w-full rounded-control object-contain border border-border/60"
              />
              {shown ? (
                <p className="text-xs font-medium text-secondary">
                  {t("content.media.size", { width: shown.width, height: shown.height })}
                </p>
              ) : null}
            </div>
          ) : preview.error ? (
            <p className="p-4 text-center text-sm text-secondary">{t("content.media.previewFailed")}</p>
          ) : (
            <div className="flex items-center justify-center gap-2 p-6 text-sm text-secondary">
              <SpinnerIcon className="motion-safe:animate-spin text-base text-action" />
              <span>{t("content.media.loadingPreview")}</span>
            </div>
          )}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <ul
          className="flex flex-col gap-1.5 rounded-panel border border-attention bg-attention-subtle p-3.5 text-sm text-attention shadow-xs"
          data-testid="media-warnings"
        >
          {warnings.map((warning, index) => (
            <li key={`${warning.code}-${index}`} className="flex items-start gap-2">
              <AlertIcon className="mt-0.5 shrink-0 text-sm" />
              <span>{checkMessage(warning, t)}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex items-center gap-3">
        <input
          id={inputId}
          type="file"
          accept="image/jpeg,image/png"
          className="peer sr-only"
          disabled={disabled || upload.isPending}
          onChange={(event) => {
            choose(event.target.files?.[0]);
            event.target.value = ""; // choosing the same file again must still fire
          }}
        />
        <label
          htmlFor={inputId}
          className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-control border border-control bg-surface px-4 py-2 text-form font-medium text-primary shadow-xs transition-colors hover:bg-surface-subtle peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus peer-disabled:cursor-not-allowed peer-disabled:opacity-60"
        >
          {upload.isPending ? (
            <SpinnerIcon className="motion-safe:animate-spin text-lg text-action" />
          ) : (
            <ImageIcon className="text-lg text-action" />
          )}
          <span>
            {upload.isPending
              ? t("content.media.uploading")
              : mediaId
                ? t("content.media.replace")
                : t("content.media.choose")}
          </span>
        </label>
      </div>

      {upload.error ? <UploadError error={upload.error} /> : null}
    </div>
  );
}
