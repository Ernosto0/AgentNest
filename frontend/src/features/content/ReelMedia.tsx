import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContentItem } from "@/api/types";
import { AlertIcon, SpinnerIcon, VideoIcon, XIcon } from "@/components/icons";
import { Button } from "@/components/Button";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useMediaPreview, usePatchContent, useUploadMedia, useUploadVideo } from "./hooks";
import { UploadError } from "./MediaUpload";
import { checkMessage } from "./messages";
import {
  REEL_MAX_DURATION_MS,
  formatUploadMegabytes,
  formatVideoTime,
  mediaContentUrl,
  validateCoverFile,
  validateVideoFile,
} from "./reel";

const REEL_WARNING_CODE: Record<string, string> = {
  ASPECT_NOT_9_16: "REEL_ASPECT_NOT_9_16",
  RESOLUTION_BELOW_RECOMMENDED: "REEL_RESOLUTION_BELOW_RECOMMENDED",
  EDIT_LIST_PRESENT: "REEL_EDIT_LIST_PRESENT",
};

/**
 * Reel media workbench: resumable/progress XHR video upload with cancel, Range-backed `<video>`
 * playback, frame scrubber for ``thumb_offset_ms``, custom JPEG cover upload, and ``share_to_feed``.
 */
export function ReelMedia({
  item,
  workspaceId,
  onCheck,
  disabled = false,
  onBusyChange,
}: {
  item: ContentItem;
  workspaceId: string;
  onCheck?: () => void;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const videoInputId = useId();
  const coverInputId = useId();
  const scrubberId = useId();
  const shareId = useId();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const patch = usePatchContent(workspaceId, item.id);
  const videoUpload = useUploadVideo(workspaceId);
  const coverUpload = useUploadMedia(workspaceId);
  const videoPreview = useMediaPreview(workspaceId, item.media_deleted ? null : item.media_asset_id);
  const coverPreview = useMediaPreview(
    workspaceId,
    item.cover_media_asset_id && !item.cover_media_deleted ? item.cover_media_asset_id : null,
  );

  const [clientError, setClientError] = useState<string | null>(null);
  const [scrubOverride, setScrubOverride] = useState<{ version: number; ms: number } | null>(null);

  const rawDurationMs = Math.min(
    REEL_MAX_DURATION_MS,
    Math.max(100, item.video_duration_ms ?? videoPreview.durationMs ?? 0),
  );
  const maxOffsetMs = Math.max(0, rawDurationMs - 100);
  const effectiveMs =
    scrubOverride !== null && scrubOverride.version === item.version
      ? Math.min(scrubOverride.ms, maxOffsetMs)
      : Math.min(item.thumb_offset_ms ?? 0, maxOffsetMs);

  const busy = disabled || videoUpload.isPending || coverUpload.isPending || patch.isPending;
  const setBusy = (next: boolean) => onBusyChange?.(next);

  const handleVideoChosen = async (file: File | undefined) => {
    if (!file) return;
    setClientError(null);
    const problem = validateVideoFile(file);
    if (problem === "type") {
      setClientError(t("content.reel.wrongFileType"));
      return;
    }
    if (problem === "size") {
      setClientError(t("content.reel.fileTooLarge"));
      return;
    }
    setBusy(true);
    try {
      const asset = await videoUpload.upload(file);
      if (!asset) return;
      await patch.mutateAsync({
        expectedVersion: item.version,
        changes: {
          media_asset_id: asset.id,
          cover_media_asset_id: null,
          thumb_offset_ms: null,
        },
      });
      setScrubOverride(null);
      onCheck?.();
    } catch {
      // Errors stay in videoUpload.error or patch.error
    } finally {
      setBusy(false);
    }
  };

  const handleCoverChosen = async (file: File | undefined) => {
    if (!file) return;
    setClientError(null);
    const problem = validateCoverFile(file);
    if (problem === "type") {
      setClientError(t("content.reel.coverWrongType"));
      return;
    }
    if (problem === "size") {
      setClientError(t("content.reel.coverTooLarge"));
      return;
    }
    setBusy(true);
    try {
      const asset = await coverUpload.mutateAsync(file);
      await patch.mutateAsync({
        expectedVersion: item.version,
        changes: { cover_media_asset_id: asset.id, thumb_offset_ms: null },
      });
      setScrubOverride(null);
      onCheck?.();
    } catch {
      // Errors stay in coverUpload.error or patch.error
    } finally {
      setBusy(false);
    }
  };

  const applyThumbOffset = async (ms: number | null) => {
    setClientError(null);
    if ((item.thumb_offset_ms ?? null) === ms && (item.cover_media_asset_id ?? null) === null) {
      setScrubOverride(null);
      return;
    }
    setBusy(true);
    try {
      await patch.mutateAsync({
        expectedVersion: item.version,
        changes: { thumb_offset_ms: ms, cover_media_asset_id: null },
      });
      setScrubOverride(null);
      onCheck?.();
    } catch {
      // Errors stay in patch.error
    } finally {
      setBusy(false);
    }
  };

  const toggleShareToFeed = async (checked: boolean) => {
    setClientError(null);
    if ((item.share_to_feed ?? true) === checked) {
      return;
    }
    setBusy(true);
    try {
      await patch.mutateAsync({
        expectedVersion: item.version,
        changes: { share_to_feed: checked },
      });
    } catch {
      // Errors stay in patch.error
    } finally {
      setBusy(false);
    }
  };

  const warnings = (videoPreview.asset?.video_warnings ?? [])
    .map((code) => REEL_WARNING_CODE[code] ?? code)
    .filter((code): code is string => Boolean(code));

  const coverSummary = item.cover_media_asset_id
    ? t("content.reel.coverUsingCustom")
    : item.thumb_offset_ms !== null && item.thumb_offset_ms !== undefined
      ? t("content.reel.coverUsingOffset", { time: formatVideoTime(item.thumb_offset_ms, true) })
      : t("content.reel.coverUsingDefault");

  const shareToFeed = item.share_to_feed ?? true;
  const durationDisplay = item.video_duration_ms ?? videoPreview.durationMs;

  return (
    <section aria-label={t("content.type.reel")} className="flex min-w-0 flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold text-primary">{t("content.type.reel")}</h3>
        <p className="mt-0.5 text-xs text-secondary">{t("content.reel.hint")}</p>
      </div>

      {item.media_asset_id && item.media_deleted ? (
        <p className="rounded-control border border-attention bg-attention-subtle p-4 text-sm text-attention shadow-xs">
          {t("content.reel.deleted")}
        </p>
      ) : null}

      {item.cover_media_asset_id && item.cover_media_deleted ? (
        <p className="rounded-control border border-attention bg-attention-subtle p-4 text-sm text-attention shadow-xs">
          {t("content.reel.coverDeleted")}
        </p>
      ) : null}

      {item.media_asset_id && !item.media_deleted ? (
        <div className="flex min-w-0 flex-col gap-3 rounded-panel border border-border bg-surface-subtle p-3">
          <div className="overflow-hidden rounded-control bg-black">
            <video
              ref={videoRef}
              controls
              playsInline
              preload="metadata"
              src={mediaContentUrl(workspaceId, item.media_asset_id)}
              poster={coverPreview.url ?? videoPreview.url ?? undefined}
              className="max-h-[50dvh] w-full object-contain"
              data-testid="reel-video-player"
            />
          </div>
          {durationDisplay !== null && durationDisplay !== undefined ? (
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-secondary tabular-nums">
              <span>{coverSummary}</span>
              <span className="font-medium text-primary">{formatVideoTime(durationDisplay)}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <div className="flex flex-col gap-1.5 rounded-panel border border-attention bg-attention-subtle p-3 text-sm text-attention">
          <p className="flex items-center gap-1.5 font-semibold">
            <AlertIcon aria-hidden="true" className="shrink-0 text-base" />
            <span>{t("content.reel.warningsLabel")}</span>
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {warnings.map((code) => (
              <li key={code}>{checkMessage({ code, params: {} }, t)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <input
          id={videoInputId}
          type="file"
          accept="video/mp4,video/quicktime,.mp4,.mov"
          className="peer sr-only"
          disabled={busy}
          onChange={(event) => {
            void handleVideoChosen(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <label
          htmlFor={videoInputId}
          className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-control border border-control bg-surface px-4 py-2 text-form font-medium text-primary shadow-xs transition-colors hover:bg-surface-subtle peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus peer-disabled:cursor-not-allowed peer-disabled:opacity-60"
        >
          {videoUpload.isPending ? (
            <SpinnerIcon className="motion-safe:animate-spin text-lg text-action" />
          ) : (
            <VideoIcon className="text-lg text-action" />
          )}
          <span>
            {videoUpload.isPending
              ? videoUpload.probing
                ? t("content.reel.probing")
                : t("content.reel.uploading", { percent: videoUpload.progress?.percent ?? 0 })
              : item.media_asset_id
                ? t("content.reel.replaceVideo")
                : t("content.reel.uploadVideo")}
          </span>
        </label>
        {videoUpload.isPending ? (
          <Button variant="secondary" onClick={videoUpload.cancel}>
            <XIcon className="text-base" />
            <span>{t("content.reel.cancelUpload")}</span>
          </Button>
        ) : null}
      </div>

      {videoUpload.isPending ? (
        <div className="flex min-w-0 flex-col gap-1.5" role="status" aria-live="polite">
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-subtle">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={videoUpload.progress?.percent ?? 0}
              className="h-full bg-action transition-all"
              style={{ width: `${videoUpload.progress?.percent ?? 0}%` }}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-secondary tabular-nums">
            <span>
              {videoUpload.probing
                ? t("content.reel.probing")
                : t("content.reel.uploading", { percent: videoUpload.progress?.percent ?? 0 })}
            </span>
            {formatUploadMegabytes(videoUpload.progress?.loaded, videoUpload.progress?.total) ? (
              <span>
                {formatUploadMegabytes(videoUpload.progress?.loaded, videoUpload.progress?.total)}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {clientError ? (
        <p role="alert" className="rounded-control border border-danger bg-danger-subtle p-3 text-sm text-danger shadow-xs">
          {clientError}
        </p>
      ) : null}
      {videoUpload.error ? <UploadError error={videoUpload.error} /> : null}
      {coverUpload.error ? <UploadError error={coverUpload.error} /> : null}
      {patch.error ? <ErrorMessage error={patch.error} /> : null}

      {item.media_asset_id && !item.media_deleted ? (
        <div className="flex min-w-0 flex-col gap-3 rounded-panel border border-border p-4">
          <div>
            <h4 className="text-sm font-semibold text-primary">{t("content.reel.coverSection")}</h4>
            <p className="mt-0.5 text-xs text-secondary">{t("content.reel.coverHint")}</p>
          </div>

          <div className="flex min-w-0 flex-col gap-2">
            <label htmlFor={scrubberId} className="text-xs font-medium text-primary tabular-nums">
              {t("content.reel.framePosition", { time: formatVideoTime(effectiveMs, true) })}
            </label>
            <input
              id={scrubberId}
              type="range"
              min={0}
              max={maxOffsetMs}
              step={100}
              value={effectiveMs}
              aria-valuetext={formatVideoTime(effectiveMs, true)}
              disabled={busy || maxOffsetMs <= 0}
              onChange={(event) => {
                const nextMs = Math.min(maxOffsetMs, Math.max(0, Number(event.target.value) || 0));
                setScrubOverride({ version: item.version, ms: nextMs });
                if (videoRef.current) {
                  videoRef.current.currentTime = nextMs / 1000;
                }
              }}
              className="min-h-11 w-full accent-action"
            />
          </div>

          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void applyThumbOffset(effectiveMs)}
            >
              {t("content.reel.useThisFrame")}
            </Button>

            <input
              id={coverInputId}
              type="file"
              accept="image/jpeg,.jpg,.jpeg"
              className="peer sr-only"
              disabled={busy}
              onChange={(event) => {
                void handleCoverChosen(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            <label
              htmlFor={coverInputId}
              className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-control border border-control bg-surface px-4 py-2 text-form font-medium text-primary shadow-xs transition-colors hover:bg-surface-subtle peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus peer-disabled:cursor-not-allowed peer-disabled:opacity-60"
            >
              {t("content.reel.uploadCover")}
            </label>

            {item.cover_media_asset_id !== null || item.thumb_offset_ms !== null ? (
              <Button variant="ghost" disabled={busy} onClick={() => void applyThumbOffset(null)}>
                {t("content.reel.useFirstFrame")}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <label
        htmlFor={shareId}
        className="flex min-h-11 cursor-pointer items-start gap-3 rounded-panel border border-border p-3.5 text-sm"
      >
        <input
          id={shareId}
          type="checkbox"
          role="switch"
          checked={shareToFeed}
          disabled={busy}
          onChange={(event) => void toggleShareToFeed(event.target.checked)}
          className="mt-1 size-5 shrink-0 accent-action"
        />
        <span className="min-w-0 flex-1">
          <span className="block font-medium text-primary">{t("content.reel.shareToFeed")}</span>
          <span className="mt-0.5 block text-xs text-secondary">{t("content.reel.shareToFeedHint")}</span>
        </span>
      </label>

      <p
        role="note"
        className="rounded-panel border border-border bg-surface-subtle p-3.5 text-xs leading-relaxed text-secondary"
      >
        {t("content.reel.notFactChecked")}
      </p>

      {patch.isPending ? (
        <p role="status" className="text-xs text-secondary">
          {t("content.reel.saving")}
        </p>
      ) : null}
    </section>
  );
}
