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

from app.core.i18n import t

# --- codes ------------------------------------------------------------------------------------

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

ERROR_CODES = (
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
WARNING_CODES = (STORY_ASPECT_NOT_9_16, OVERLAY_TOO_LONG)
ALL_CODES = ERROR_CODES + WARNING_CODES

# --- limits -----------------------------------------------------------------------------------

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
    "story_image": "publish_story_image",
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

    # Media: both formats are image posts.
    if facts.media is None:
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
