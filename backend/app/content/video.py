"""Pure Reel media rules. Sources and deliberate exceptions: ADR-028."""

import math
from dataclasses import dataclass
from typing import Any

from app.content.video_limits import MAX_DURATION_MS, MIN_DURATION_MS
from app.integrations.video.base import VideoFacts

MAX_VIDEO_BYTES = 300_000_000
MIN_FPS = 23
MAX_FPS = 60
FPS_TOLERANCE = 0.05
MAX_WIDTH = 1920
MIN_DIMENSION = 64
MIN_ASPECT = 0.1
MAX_ASPECT = 10
MAX_BITRATE_BPS = 25_000_000
MAX_AUDIO_SAMPLE_RATE = 48000
RECOMMENDED_ASPECT = 9 / 16
ASPECT_TOLERANCE = 0.02
RECOMMENDED_WIDTH = 540
REJECT_EDIT_LISTS = False
VIDEO_CODECS = ("h264", "hevc")
AUDIO_CODEC = "aac"
INTERLACED_FIELDS = ("tt", "bb", "tb", "bt")


@dataclass(frozen=True)
class VideoLimits:
    min_duration_ms: int = MIN_DURATION_MS
    max_duration_ms: int = MAX_DURATION_MS
    min_fps: float = MIN_FPS
    max_fps: float = MAX_FPS
    fps_tolerance: float = FPS_TOLERANCE
    max_width: int = MAX_WIDTH
    min_dimension: int = MIN_DIMENSION
    min_aspect: float = MIN_ASPECT
    max_aspect: float = MAX_ASPECT
    max_bitrate_bps: int = MAX_BITRATE_BPS
    max_audio_sample_rate: int = MAX_AUDIO_SAMPLE_RATE
    reject_edit_lists: bool = REJECT_EDIT_LISTS


@dataclass(frozen=True)
class Issue:
    code: str
    limit: Any = None
    actual: Any = None


@dataclass(frozen=True)
class VideoVerdict:
    issues: tuple[Issue, ...]
    warnings: tuple[str, ...]

    @property
    def primary(self) -> str | None:
        return self.issues[0].code if self.issues else None


def validate_video(facts: VideoFacts, *, byte_size: int, limits: VideoLimits) -> VideoVerdict:
    issues: list[Issue] = []
    warnings: list[str] = []

    def check(bad: bool, code: str, limit: Any = None, actual: Any = None) -> None:
        if bad:
            issues.append(Issue(code, limit, actual))

    check(byte_size == 0, "EMPTY_FILE", 1, byte_size)
    check(
        facts.container not in ("mp4", "mov"), "UNSUPPORTED_CONTAINER", "mp4,mov", facts.container
    )
    check(facts.video_stream_count == 0, "NO_VIDEO_STREAM", 1, facts.video_stream_count)
    check(facts.video_stream_count > 1, "MULTIPLE_VIDEO_STREAMS", 1, facts.video_stream_count)
    check(
        facts.video_codec not in VIDEO_CODECS,
        "UNSUPPORTED_VIDEO_CODEC",
        VIDEO_CODECS,
        facts.video_codec,
    )
    check(
        any(c != AUDIO_CODEC for c in facts.audio_codecs),
        "UNSUPPORTED_AUDIO_CODEC",
        AUDIO_CODEC,
        facts.audio_codecs,
    )
    if facts.audio_codecs:
        check(
            not 0 < facts.audio_sample_rate <= limits.max_audio_sample_rate,
            "UNSUPPORTED_AUDIO_SAMPLE_RATE",
            limits.max_audio_sample_rate,
            facts.audio_sample_rate,
        )
        check(
            facts.audio_channels not in (1, 2),
            "UNSUPPORTED_AUDIO_CHANNELS",
            (1, 2),
            facts.audio_channels,
        )
    check(
        not facts.pix_fmt.startswith(("yuv420p", "yuvj420p")),
        "UNSUPPORTED_PIXEL_FORMAT",
        "4:2:0",
        facts.pix_fmt,
    )
    check(facts.field_order in INTERLACED_FIELDS, "INTERLACED", "progressive", facts.field_order)
    check(facts.duration_ms <= 0, "DURATION_UNKNOWN", None, facts.duration_ms)
    check(
        0 < facts.duration_ms < limits.min_duration_ms,
        "DURATION_TOO_SHORT",
        limits.min_duration_ms,
        facts.duration_ms,
    )
    check(
        facts.duration_ms > limits.max_duration_ms,
        "DURATION_TOO_LONG",
        limits.max_duration_ms,
        facts.duration_ms,
    )
    check(
        not math.isfinite(facts.frame_rate)
        or not limits.min_fps - limits.fps_tolerance
        <= facts.frame_rate
        <= limits.max_fps + limits.fps_tolerance,
        "FRAME_RATE_OUT_OF_RANGE",
        (limits.min_fps, limits.max_fps),
        facts.frame_rate if math.isfinite(facts.frame_rate) else None,
    )
    check(facts.width > limits.max_width, "WIDTH_TOO_LARGE", limits.max_width, facts.width)
    check(
        min(facts.width, facts.height) < limits.min_dimension,
        "RESOLUTION_TOO_LOW",
        limits.min_dimension,
        (facts.width, facts.height),
    )
    ratio = facts.width / facts.height if facts.height > 0 else 0
    check(
        not limits.min_aspect <= ratio <= limits.max_aspect,
        "ASPECT_RATIO_OUT_OF_RANGE",
        (limits.min_aspect, limits.max_aspect),
        ratio,
    )
    check(
        facts.video_bitrate_bps > limits.max_bitrate_bps,
        "BITRATE_TOO_HIGH",
        limits.max_bitrate_bps,
        facts.video_bitrate_bps,
    )
    check(not facts.moov_first, "MOOV_NOT_AT_FRONT")
    if facts.has_edit_list:
        if limits.reject_edit_lists:
            issues.append(Issue("EDIT_LIST_PRESENT"))
        else:
            warnings.append("EDIT_LIST_PRESENT")
    if abs(ratio / RECOMMENDED_ASPECT - 1) > ASPECT_TOLERANCE:
        warnings.append("ASPECT_NOT_9_16")
    if facts.width < RECOMMENDED_WIDTH:
        warnings.append("RESOLUTION_BELOW_RECOMMENDED")
    return VideoVerdict(tuple(issues), tuple(warnings))
