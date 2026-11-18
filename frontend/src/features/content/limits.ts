/** Instagram's caption limit, as the server checks it at submit (content/validation.py, V-05 to verify). */
export const CAPTION_MAX_CHARS = 2200;
/** Storage guards of the API (content/schemas.py). */
export const TITLE_MAX = 200;
export const OVERLAY_ITEMS_MAX = 10;
export const OVERLAY_ITEM_MAX = 500;
export const NOTES_MAX = 2000;
/** `objective` of a generation request (content/schemas.py). */
export const OBJECTIVE_MAX = 1000;
/** Max reel video byte size (content/video.py). */
export const VIDEO_MAX_BYTES = 300_000_000;
/** Max reel custom cover JPEG byte size (content/validation.py). */
export const REEL_COVER_MAX_BYTES = 8_000_000;
