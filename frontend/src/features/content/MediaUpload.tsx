import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { AppError } from "@/api/errors";
import type { ContentCheckItem, ContentType, MediaAsset } from "@/api/types";
import { ErrorMessage } from "@/components/ErrorMessage";
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
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
          {t("content.media.tooLarge", { limit })}
        </p>
      );
    }
    const reason = typeof error.params.reason === "string" ? error.params.reason : null;
    if (error.code === "MEDIA_INVALID" && reason && ["EMPTY_FILE", "NOT_AN_IMAGE", "CORRUPT_IMAGE", "TOO_MANY_PIXELS"].includes(reason)) {
      return (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-300">
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
  onUploaded,
  warnings = [],
  disabled = false,
}: MediaUploadProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const upload = useUploadMedia(workspaceId);
  const preview = useMediaPreview(workspaceId, mediaId);
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
    <div className="flex flex-col gap-2" data-testid="media-upload">
      <span className="text-sm font-medium text-slate-800">{t("content.media.label")}</span>
      <p className="text-sm text-slate-600">
        {contentType === "story_image" ? t("content.media.storyHint") : t("content.media.feedHint")}
      </p>

      {mediaId ? (
        <div className="overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200">
          {preview.url ? (
            <img
              src={preview.url}
              alt={t("content.media.previewAlt")}
              className="mx-auto max-h-80 w-auto max-w-full object-contain"
            />
          ) : preview.error ? (
            <p className="p-4 text-sm text-slate-700">{t("content.media.previewFailed")}</p>
          ) : (
            <p className="p-4 text-sm text-slate-700">{t("content.media.loadingPreview")}</p>
          )}
        </div>
      ) : null}
      {shown ? (
        <p className="text-sm text-slate-600">
          {t("content.media.size", { width: shown.width, height: shown.height })}
        </p>
      ) : null}

      {warnings.length > 0 ? (
        <ul className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="media-warnings">
          {warnings.map((warning, index) => (
            <li key={`${warning.code}-${index}`}>{checkMessage(warning, t)}</li>
          ))}
        </ul>
      ) : null}

      <div>
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
          className="inline-flex min-h-11 cursor-pointer items-center justify-center rounded-lg bg-white px-4 py-2 text-base font-medium text-slate-900 ring-1 ring-slate-300 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-indigo-600 peer-disabled:cursor-not-allowed peer-disabled:text-slate-400"
        >
          {upload.isPending
            ? t("content.media.uploading")
            : mediaId
              ? t("content.media.replace")
              : t("content.media.choose")}
        </label>
      </div>

      {upload.error ? <UploadError error={upload.error} /> : null}
    </div>
  );
}
