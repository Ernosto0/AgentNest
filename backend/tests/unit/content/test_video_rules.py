"""Meta-derived numeric boundaries, all rejection codes and advisory warnings."""

from dataclasses import replace

import pytest

from app.content.video import VideoLimits, validate_video
from app.integrations.video.base import VideoFacts


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("duration_ms", 0, "DURATION_UNKNOWN"),
        ("duration_ms", 2999, "DURATION_TOO_SHORT"),
        ("duration_ms", 900001, "DURATION_TOO_LONG"),
        ("frame_rate", 22.9, "FRAME_RATE_OUT_OF_RANGE"),
        ("frame_rate", 60.1, "FRAME_RATE_OUT_OF_RANGE"),
        ("frame_rate", float("nan"), "FRAME_RATE_OUT_OF_RANGE"),
        ("width", 1921, "WIDTH_TOO_LARGE"),
        ("height", 63, "RESOLUTION_TOO_LOW"),
        ("width", 100, "ASPECT_RATIO_OUT_OF_RANGE"),
        ("height", 64, "ASPECT_RATIO_OUT_OF_RANGE"),
        ("video_bitrate_bps", 25000001, "BITRATE_TOO_HIGH"),
        ("audio_sample_rate", 48001, "UNSUPPORTED_AUDIO_SAMPLE_RATE"),
        ("audio_channels", 3, "UNSUPPORTED_AUDIO_CHANNELS"),
        ("pix_fmt", "yuv422p", "UNSUPPORTED_PIXEL_FORMAT"),
        ("pix_fmt", "yuv444p", "UNSUPPORTED_PIXEL_FORMAT"),
        ("field_order", "tt", "INTERLACED"),
        ("field_order", "bb", "INTERLACED"),
        ("field_order", "tb", "INTERLACED"),
        ("field_order", "bt", "INTERLACED"),
        ("video_codec", "vp9", "UNSUPPORTED_VIDEO_CODEC"),
        ("audio_codecs", ("aac", "mp3"), "UNSUPPORTED_AUDIO_CODEC"),
        ("video_stream_count", 0, "NO_VIDEO_STREAM"),
        ("video_stream_count", 2, "MULTIPLE_VIDEO_STREAMS"),
        ("container", "3gp", "UNSUPPORTED_CONTAINER"),
        ("moov_first", False, "MOOV_NOT_AT_FRONT"),
    ],
)
def test_rejections(field, value, code):
    verdict = validate_video(
        replace(VideoFacts(), **{field: value}), byte_size=1000, limits=VideoLimits()
    )
    assert code in [i.code for i in verdict.issues]


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_ms": 3000},
        {"duration_ms": 900000},
        {"frame_rate": 23},
        {"frame_rate": 60},
        {"frame_rate": 23.976},
        {"frame_rate": 59.94},
        {"width": 1920},
        {"video_bitrate_bps": 25000000},
        {"width": 100, "height": 1000},
        {"width": 1000, "height": 100},
        {"audio_sample_rate": 48000},
        {"audio_channels": 1},
        {"audio_channels": 2},
        {"pix_fmt": "yuv420p10le"},
        {"pix_fmt": "yuvj420p"},
        {"audio_codecs": (), "audio_sample_rate": 0, "audio_channels": 0},
        {"video_codec": "hevc"},
        {"container": "mov"},
    ],
)
def test_allowed_boundaries(overrides):
    assert not validate_video(
        replace(VideoFacts(), **overrides), byte_size=1000, limits=VideoLimits()
    ).issues


def test_all_issues_and_primary_and_warnings():
    verdict = validate_video(
        replace(
            VideoFacts(), width=400, height=400, duration_ms=1, has_edit_list=True, moov_first=False
        ),
        byte_size=0,
        limits=VideoLimits(),
    )
    assert [i.code for i in verdict.issues] == [
        "EMPTY_FILE",
        "DURATION_TOO_SHORT",
        "MOOV_NOT_AT_FRONT",
    ]
    assert verdict.primary == "EMPTY_FILE"
    assert set(verdict.warnings) == {
        "EDIT_LIST_PRESENT",
        "ASPECT_NOT_9_16",
        "RESOLUTION_BELOW_RECOMMENDED",
    }
    assert (
        validate_video(
            replace(VideoFacts(), has_edit_list=True),
            byte_size=1,
            limits=VideoLimits(reject_edit_lists=True),
        ).primary
        == "EDIT_LIST_PRESENT"
    )
