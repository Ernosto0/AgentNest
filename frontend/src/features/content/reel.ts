import type { TFunction } from "i18next";
import { API_BASE } from "@/api/client";
import { REEL_COVER_MAX_BYTES, VIDEO_MAX_BYTES } from "./limits";

export { REEL_COVER_MAX_BYTES, VIDEO_MAX_BYTES };

export const REEL_MIN_DURATION_MS = 3_000;
export const REEL_MAX_DURATION_MS = 900_000;

const VIDEO_MIME = new Set(["video/mp4", "video/quicktime"]);
const VIDEO_EXT = /\.(?:mp4|mov)$/i;
const JPEG_MIME = new Set(["image/jpeg", "image/jpg"]);
const JPEG_EXT = /\.jpe?g$/i;

export type VideoFileError = "type" | "size";
export type CoverFileError = "type" | "size";

export function isAcceptedVideoFile(file: Pick<File, "name" | "type">): boolean {
  const mime = file.type.trim().toLowerCase();
  if (mime && VIDEO_MIME.has(mime)) return true;
  if ((!mime || mime === "application/octet-stream") && VIDEO_EXT.test(file.name)) return true;
  return false;
}

export function validateVideoFile(file: Pick<File, "name" | "type" | "size">): VideoFileError | null {
  if (!isAcceptedVideoFile(file)) return "type";
  if (file.size > VIDEO_MAX_BYTES) return "size";
  return null;
}

export function isAcceptedCoverFile(file: Pick<File, "name" | "type">): boolean {
  const mime = file.type.trim().toLowerCase();
  if (mime && JPEG_MIME.has(mime)) return true;
  if ((!mime || mime === "application/octet-stream") && JPEG_EXT.test(file.name)) return true;
  return false;
}

export function validateCoverFile(file: Pick<File, "name" | "type" | "size">): CoverFileError | null {
  if (!isAcceptedCoverFile(file)) return "type";
  if (file.size > REEL_COVER_MAX_BYTES) return "size";
  return null;
}

/** Format milliseconds as m:ss (or m:ss.d when decisecond=true). */
export function formatVideoTime(ms: number | null | undefined, withDecisecond = false): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "0:00";
  const clamped = Math.round(ms);
  const totalSeconds = Math.floor(clamped / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  if (!withDecisecond) return `${minutes}:${seconds}`;
  const tenths = Math.floor((clamped % 1000) / 100);
  return `${minutes}:${seconds}.${tenths}`;
}

export function formatUploadMegabytes(
  loaded: number | null | undefined,
  total: number | null | undefined,
): string | null {
  if (
    loaded === null ||
    loaded === undefined ||
    total === null ||
    total === undefined ||
    !Number.isFinite(loaded) ||
    !Number.isFinite(total) ||
    total <= 0
  ) {
    return null;
  }
  return `${(loaded / 1_000_000).toFixed(1)} MB / ${(total / 1_000_000).toFixed(1)} MB`;
}

export function mediaContentUrl(workspaceId: string, mediaId: string): string {
  return `${API_BASE}/api/v1/workspaces/${workspaceId}/media/${mediaId}/content`;
}

export const REEL_CODES = [
  "REEL_DURATION_OUT_OF_RANGE",
  "REEL_COVER_OFFSET_INVALID",
  "REEL_COVER_TOO_LARGE",
  "REEL_ASPECT_NOT_9_16",
  "REEL_RESOLUTION_BELOW_RECOMMENDED",
  "REEL_EDIT_LIST_PRESENT",
] as const;

export function reelMessage(code: string, params: Record<string, unknown>, t: TFunction): string | null {
  if (!(REEL_CODES as readonly string[]).includes(code)) return null;
  return t(`content.editor.checks.${code}`, { ...params });
}
