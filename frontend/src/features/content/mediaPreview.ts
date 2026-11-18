import type { MediaAsset } from "@/api/types";

/** Only an image or a video's JPEG thumbnail may enter the image-blob cache. */
export function mediaPreviewId(asset: Pick<MediaAsset, "id" | "kind" | "thumbnail_media_asset_id"> | null): string | null {
  if (!asset) return null;
  if (asset.kind === "video") return asset.thumbnail_media_asset_id ?? null;
  return asset.kind === "video_thumbnail" ? null : asset.id;
}
