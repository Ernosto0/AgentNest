"""Submit-time validation of a content item (workflows.md section E step 4.1, plan.md G17).

Pure: ``validate_submission`` looks only at the ``SubmitFacts`` it is given, so every rule is
a unit test (AC-D3). The service gathers the facts (media row, account, claim check, schedule,
quota) and decides what to do with the result.

Blocking codes (``errors``) keep the item a ``draft``; ``warnings`` never block.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.content.video_limits import MAX_DURATION_MS, MIN_DURATION_MS
from app.core.i18n import t

# --- codes ------------------------------------------------------------------------------------

TEMPLATE_IMAGE_STALE = "TEMPLATE_IMAGE_STALE"
CONTENT_MEDIA_REQUIRED = "CONTENT_MEDIA_REQUIRED"
MEDIA_NOT_READY = "MEDIA_NOT_READY"
CAPTION_REQUIRED = "CAPTION_REQUIRED"
CAPTION_TOO_LONG = "CAPTION_TOO_LONG"
CAPTION_NOT_ALLOWED = "CAPTION_NOT_ALLOWED"
ASPECT_RATIO_OUT_OF_RANGE = "ASPECT_RATIO_OUT_OF_RANGE"
CLAIM_VALIDATION_FAILED = "CLAIM_VALIDATION_FAILED"
SCHEDULE_IN_PAST = "SCHEDULE_IN_PAST"
SCHEDULE_TOO_FAR = "SCHEDULE_TOO_FAR"
SCHEDULE_TIME_NONEXISTENT = "SCHEDULE_TIME_NONEXISTENT"
SCHEDULE_TOO_SOON_FOR_APPROVAL = "SCHEDULE_TOO_SOON_FOR_APPROVAL"
ACCOUNT_NOT_CONNECTED = "ACCOUNT_NOT_CONNECTED"
CAPABILITY_MISSING = "CAPABILITY_MISSING"
PUBLISH_QUOTA_FORECAST_EXCEEDED = "PUBLISH_QUOTA_FORECAST_EXCEEDED"

STORY_ASPECT_NOT_9_16 = "STORY_ASPECT_NOT_9_16"
OVERLAY_TOO_LONG = "OVERLAY_TOO_LONG"

CAROUSEL_TOO_FEW_ITEMS = "CAROUSEL_TOO_FEW_ITEMS"
CAROUSEL_TOO_MANY_ITEMS = "CAROUSEL_TOO_MANY_ITEMS"
CAROUSEL_MIXED_ASPECT_RATIO = "CAROUSEL_MIXED_ASPECT_RATIO"

REEL_DURATION_OUT_OF_RANGE = "REEL_DURATION_OUT_OF_RANGE"
REEL_COVER_OFFSET_INVALID = "REEL_COVER_OFFSET_INVALID"
REEL_COVER_TOO_LARGE = "REEL_COVER_TOO_LARGE"
REEL_ASPECT_NOT_9_16 = "REEL_ASPECT_NOT_9_16"
REEL_RESOLUTION_BELOW_RECOMMENDED = "REEL_RESOLUTION_BELOW_RECOMMENDED"
REEL_EDIT_LIST_PRESENT = "REEL_EDIT_LIST_PRESENT"

ERROR_CODES = (
    CAROUSEL_TOO_FEW_ITEMS,
    CAROUSEL_TOO_MANY_ITEMS,
    CAROUSEL_MIXED_ASPECT_RATIO,
    REEL_DURATION_OUT_OF_RANGE,
    REEL_COVER_OFFSET_INVALID,
    REEL_COVER_TOO_LARGE,
    TEMPLATE_IMAGE_STALE,
    CONTENT_MEDIA_REQUIRED,
    MEDIA_NOT_READY,
    CAPTION_REQUIRED,
    CAPTION_TOO_LONG,
    CAPTION_NOT_ALLOWED,
    ASPECT_RATIO_OUT_OF_RANGE,
    CLAIM_VALIDATION_FAILED,
    SCHEDULE_IN_PAST,
    SCHEDULE_TOO_FAR,
    SCHEDULE_TIME_NONEXISTENT,
    SCHEDULE_TOO_SOON_FOR_APPROVAL,
    ACCOUNT_NOT_CONNECTED,
    CAPABILITY_MISSING,
    PUBLISH_QUOTA_FORECAST_EXCEEDED,
)
WARNING_CODES = (
    STORY_ASPECT_NOT_9_16,
    OVERLAY_TOO_LONG,
    REEL_ASPECT_NOT_9_16,
    REEL_RESOLUTION_BELOW_RECOMMENDED,
    REEL_EDIT_LIST_PRESENT,
)
ALL_CODES = ERROR_CODES + WARNING_CODES

# --- limits -----------------------------------------------------------------------------------

CAROUSEL_MIN_ITEMS = 2
CAROUSEL_MAX_ITEMS = 10
CAROUSEL_ASPECT_TOLERANCE = 0.02

CAPTION_MAX_CHARS = 2200  # Instagram's caption limit (V-05, to verify)
FEED_ASPECT_MIN = 4 / 5  # width / height
FEED_ASPECT_MAX = 1.91
STORY_ASPECT = 9 / 16
STORY_ASPECT_TOLERANCE = 0.02  # relative
OVERLAY_MAX_LINES = 3  # agent-runtime.md section 5: <= 3 lines of <= 40 characters
OVERLAY_MAX_LINE_CHARS = 40

# Capability flag (``social_accounts.capabilities``) that publishing each content type needs.
CAPABILITY_FOR_TYPE = {
    "feed_image": "publish_feed_image",
    "feed_carousel": "publish_feed_carousel",
    "story_image": "publish_story_image",
    "reel": "publish_reel",
}

REEL_COVER_MAX_BYTES = 8_000_000
REEL_VIDEO_WARNINGS = {
    "ASPECT_NOT_9_16": REEL_ASPECT_NOT_9_16,
    "RESOLUTION_BELOW_RECOMMENDED": REEL_RESOLUTION_BELOW_RECOMMENDED,
    "EDIT_LIST_PRESENT": REEL_EDIT_LIST_PRESENT,
}


# --- facts and result -------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    code: str
    field: str | None = None
    params: Mapping[str, Any] = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class MediaFacts:
    status: str
    width: int
    height: int


@dataclass(frozen=True)
class ReelVideoFacts:
    status: str
    kind: str
    duration_ms: int | None
    warnings: Sequence[str] = ()


@dataclass(frozen=True)
class ReelCoverFacts:
    status: str
    kind: str
    mime_type: str
    byte_size: int


@dataclass(frozen=True)
class ReelFacts:
    video: ReelVideoFacts | None
    cover: ReelCoverFacts | None = None
    thumb_offset_ms: int | None = None


@dataclass(frozen=True)
class AccountFacts:
    connected: bool
    capabilities: Mapping[str, Any]


@dataclass(frozen=True)
class SubmitFacts:
    content_type: str
    caption: str | None
    overlay_text_suggestions: Sequence[str]
    media: MediaFacts | None  # ``None``: no media attached (or not of this workspace)
    # The blocking ``grounding`` issues over caption and overlays (not the verified values).
    claim_issues: Sequence[Mapping[str, Any]]
    # The ``SCHEDULE_*`` error of the requested schedule (``None`` when it is acceptable, or
    # when no schedule was given, as in a dry run).
    schedule_error: Issue | None
    account: AccountFacts | None  # ``None``: no usable account in the workspace
    quota_exceeded: bool
    stale_template_keys: tuple[str, ...] = ()
    carousel_media: Sequence[MediaFacts] | None = None
    reel: ReelFacts | None = None


@dataclass(frozen=True)
class SubmitValidation:
    errors: tuple[Issue, ...]
    warnings: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def as_dict(issue: Issue, locale: str | None = None) -> dict[str, Any]:
    """An issue as the API (and the stored report) show it. With a ``locale`` it carries the
    localised ``message``."""
    out: dict[str, Any] = {"code": issue.code, "field": issue.field, "params": dict(issue.params)}
    if locale is not None:
        out["message"] = t(f"content.issue.{issue.code}", locale, **issue.params)
    return out


def _overlay_too_long(suggestion: str) -> bool:
    lines = suggestion.splitlines() or [suggestion]
    return len(lines) > OVERLAY_MAX_LINES or any(
        len(line) > OVERLAY_MAX_LINE_CHARS for line in lines
    )


def validate_submission(facts: SubmitFacts) -> SubmitValidation:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    is_story = facts.content_type == "story_image"

    if facts.stale_template_keys:
        stale_field = (
            "media_asset_ids"
            if facts.content_type == "feed_carousel"
            else ("cover_media_asset_id" if facts.content_type == "reel" else "media_asset_id")
        )
        errors.append(
            Issue(
                TEMPLATE_IMAGE_STALE,
                stale_field,
                {"keys": list(facts.stale_template_keys)},
            )
        )
    # Media: feed/story use an image, carousels an image list, reels a video plus optional cover.
    if facts.content_type == "reel":
        reel = facts.reel
        video = reel.video if reel is not None else None
        offset = reel.thumb_offset_ms if reel is not None else None
        if video is None:
            errors.append(Issue(CONTENT_MEDIA_REQUIRED, "media_asset_id"))
            if offset is not None and offset < 0:
                errors.append(
                    Issue(
                        REEL_COVER_OFFSET_INVALID,
                        "thumb_offset_ms",
                        {"thumb_offset_ms": offset, "duration_ms": None},
                    )
                )
        elif video.status != "ready" or video.kind != "video":
            errors.append(Issue(MEDIA_NOT_READY, "media_asset_id", {"status": video.status}))
        else:
            duration_ms = video.duration_ms
            if duration_ms is None or not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS:
                errors.append(
                    Issue(
                        REEL_DURATION_OUT_OF_RANGE,
                        "media_asset_id",
                        {
                            "duration_ms": duration_ms,
                            "min_ms": MIN_DURATION_MS,
                            "max_ms": MAX_DURATION_MS,
                        },
                    )
                )
            if offset is not None and (offset < 0 or duration_ms is None or offset >= duration_ms):
                errors.append(
                    Issue(
                        REEL_COVER_OFFSET_INVALID,
                        "thumb_offset_ms",
                        {"thumb_offset_ms": offset, "duration_ms": duration_ms},
                    )
                )
            for code in video.warnings:
                mapped = REEL_VIDEO_WARNINGS.get(code)
                if mapped is not None:
                    warnings.append(Issue(mapped, "media_asset_id"))
        if reel is not None and reel.cover is not None:
            cover = reel.cover
            if cover.status != "ready" or cover.kind != "image" or cover.mime_type != "image/jpeg":
                errors.append(
                    Issue(MEDIA_NOT_READY, "cover_media_asset_id", {"status": cover.status})
                )
            if cover.byte_size > REEL_COVER_MAX_BYTES:
                errors.append(
                    Issue(
                        REEL_COVER_TOO_LARGE,
                        "cover_media_asset_id",
                        {"byte_size": cover.byte_size, "max_bytes": REEL_COVER_MAX_BYTES},
                    )
                )
    elif facts.content_type == "feed_carousel":
        images = facts.carousel_media or ()
        count = len(images)
        if not count:
            errors.append(Issue(CONTENT_MEDIA_REQUIRED, "media_asset_ids"))
        elif count < CAROUSEL_MIN_ITEMS:
            errors.append(
                Issue(
                    CAROUSEL_TOO_FEW_ITEMS,
                    "media_asset_ids",
                    {"count": count, "min": CAROUSEL_MIN_ITEMS},
                )
            )
        if count > CAROUSEL_MAX_ITEMS:
            errors.append(
                Issue(
                    CAROUSEL_TOO_MANY_ITEMS,
                    "media_asset_ids",
                    {"count": count, "max": CAROUSEL_MAX_ITEMS},
                )
            )
        positions = []
        for index, image in enumerate(images):
            field = f"media_asset_ids.{index}"
            ratio = image.width / image.height
            if image.status != "ready":
                errors.append(Issue(MEDIA_NOT_READY, field, {"status": image.status}))
            if not FEED_ASPECT_MIN <= ratio <= FEED_ASPECT_MAX:
                errors.append(
                    Issue(
                        ASPECT_RATIO_OUT_OF_RANGE,
                        field,
                        {"width": image.width, "height": image.height},
                    )
                )
            first_ratio = images[0].width / images[0].height
            if index and abs(ratio - first_ratio) / first_ratio > CAROUSEL_ASPECT_TOLERANCE:
                positions.append(index)
        if positions:
            errors.append(
                Issue(CAROUSEL_MIXED_ASPECT_RATIO, "media_asset_ids", {"positions": positions})
            )
    elif facts.media is None:
        errors.append(Issue(CONTENT_MEDIA_REQUIRED, "media_asset_id"))
    elif facts.media.status != "ready":
        errors.append(Issue(MEDIA_NOT_READY, "media_asset_id", {"status": facts.media.status}))
    else:
        ratio = facts.media.width / facts.media.height
        if is_story:
            if abs(ratio - STORY_ASPECT) / STORY_ASPECT > STORY_ASPECT_TOLERANCE:
                warnings.append(
                    Issue(
                        STORY_ASPECT_NOT_9_16,
                        "media_asset_id",
                        {"width": facts.media.width, "height": facts.media.height},
                    )
                )
        elif not FEED_ASPECT_MIN <= ratio <= FEED_ASPECT_MAX:
            errors.append(
                Issue(
                    ASPECT_RATIO_OUT_OF_RANGE,
                    "media_asset_id",
                    {"width": facts.media.width, "height": facts.media.height},
                )
            )

    # Text: a feed post needs a caption, a story publishes none (the overlay text is a
    # suggestion for the image itself, plan.md G5).
    caption = facts.caption.strip() if facts.caption else ""
    if is_story:
        if caption:
            errors.append(Issue(CAPTION_NOT_ALLOWED, "caption"))
        for index, suggestion in enumerate(facts.overlay_text_suggestions):
            if _overlay_too_long(suggestion):
                warnings.append(Issue(OVERLAY_TOO_LONG, f"overlay_text_suggestions.{index}"))
    elif not caption:
        errors.append(Issue(CAPTION_REQUIRED, "caption"))
    elif len(caption) > CAPTION_MAX_CHARS:
        errors.append(
            Issue(
                CAPTION_TOO_LONG,
                "caption",
                {"length": len(caption), "max": CAPTION_MAX_CHARS},
            )
        )

    # Claims (INV-02): whatever the validator found in the caption or an overlay suggestion.
    if facts.claim_issues:
        errors.append(
            Issue(CLAIM_VALIDATION_FAILED, None, {"issues": [dict(i) for i in facts.claim_issues]})
        )

    if facts.schedule_error is not None:
        errors.append(facts.schedule_error)

    if facts.account is None or not facts.account.connected:
        errors.append(Issue(ACCOUNT_NOT_CONNECTED, "social_account_id"))
    elif facts.account.capabilities.get(CAPABILITY_FOR_TYPE[facts.content_type]) is not True:
        errors.append(
            Issue(
                CAPABILITY_MISSING,
                "social_account_id",
                {"capability": CAPABILITY_FOR_TYPE[facts.content_type]},
            )
        )

    if facts.quota_exceeded:
        errors.append(Issue(PUBLISH_QUOTA_FORECAST_EXCEEDED, "scheduled_at"))

    return SubmitValidation(errors=tuple(errors), warnings=tuple(warnings))
