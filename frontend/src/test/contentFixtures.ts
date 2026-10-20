import type { ContentIssue, ContentItem, MediaAsset } from "@/api/types";

export const CONTENT_ID = "c5000000-0000-4000-8000-000000000001";
export const MEDIA_ID = "e5000000-0000-4000-8000-000000000001";

export function contentItem(overrides: Partial<ContentItem> = {}): ContentItem {
  return {
    id: CONTENT_ID,
    content_type: "feed_image",
    status: "draft",
    version: 1,
    title: "Yeni dönem kampanyası",
    objective: null,
    caption: "Aylık üyelik şimdi çok uygun!",
    overlay_text_suggestions: [],
    visual_notes: null,
    social_account_id: null,
    media_asset_id: null,
    scheduled_at: null,
    schedule_local: null,
    approval_id: null,
    approval: null,
    operation: null,
    hold_reason: null,
    rejection_note: null,
    validation: { passed: true, issues: [], stale: false, errors: [], warnings: [] },
    generation: null,
    published_at: null,
    external_media_id: null,
    external_permalink: null,
    last_error_code: null,
    created_by_user_id: "99999999-9999-4999-8999-999999999999",
    created_at: "2026-10-15T12:00:00Z",
    updated_at: "2026-10-15T12:05:00Z",
    is_simulated: true,
    ...overrides,
  };
}

export function claimIssue(overrides: Partial<ContentIssue> = {}): ContentIssue {
  return {
    code: "MONEY",
    field: "caption",
    span: [0, 10],
    text: "5.000 ₺ / ay",
    matches_verified: false,
    fact_key: null,
    ...overrides,
  };
}

export function mediaAsset(overrides: Partial<MediaAsset> = {}): MediaAsset {
  return {
    id: MEDIA_ID,
    status: "ready",
    width: 1080,
    height: 1350,
    mime_type: "image/jpeg",
    byte_size: 200_000,
    original_filename: "foto.jpg",
    rejection_code: null,
    created_at: "2026-10-15T12:06:00Z",
    ...overrides,
  };
}
