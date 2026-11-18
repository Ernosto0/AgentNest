"""Video inspection contract. All supplied media is untrusted."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class VideoFacts:
    container: Literal["mp4", "mov"] = "mp4"
    major_brand: str = "isom"
    duration_ms: int = 10000
    width: int = 1080
    height: int = 1920
    video_codec: str = "h264"
    pix_fmt: str = "yuv420p"
    field_order: str = "progressive"
    frame_rate: float = 30
    video_bitrate_bps: int = 8000000
    audio_codecs: tuple[str, ...] = ("aac",)
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    video_stream_count: int = 1
    moov_first: bool = True
    has_edit_list: bool = False


class VideoProbeFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class VideoProbeUnavailable(Exception):
    """Transient inability to inspect; never a media rejection."""


class VideoProber(Protocol):
    def probe(self, path: Path) -> VideoFacts: ...
    def extract_frame(self, path: Path, at_ms: int, max_width: int) -> bytes: ...
