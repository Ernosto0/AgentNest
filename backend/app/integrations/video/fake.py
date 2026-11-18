"""Deterministic test/demo adapter; production configuration rejects it."""

import io
import json
from dataclasses import fields
from pathlib import Path

from PIL import Image

from app.integrations.video.base import VideoFacts, VideoProbeFailed


class FakeVideoProber:
    def probe(self, path: Path) -> VideoFacts:
        with path.open("rb") as file:
            line = file.readline(16384)
        if not line.startswith(b"FAKEVIDEO1 "):
            raise VideoProbeFailed("NOT_A_VIDEO")
        try:
            overrides = json.loads(line[11:])
            if not isinstance(overrides, dict) or set(overrides) - {
                f.name for f in fields(VideoFacts)
            }:
                raise ValueError
            if "audio_codecs" in overrides:
                overrides["audio_codecs"] = tuple(overrides["audio_codecs"])
            defaults = VideoFacts()
            for name, value in overrides.items():
                expected = getattr(defaults, name)
                if name == "frame_rate":
                    if not isinstance(value, int | float) or isinstance(value, bool):
                        raise ValueError
                elif not isinstance(value, type(expected)):
                    raise ValueError
            if any(not isinstance(codec, str) for codec in overrides.get("audio_codecs", ())):
                raise ValueError
            return VideoFacts(**overrides)
        except (ValueError, TypeError, RecursionError) as exc:
            raise VideoProbeFailed("CORRUPT_VIDEO") from exc

    def extract_frame(self, path: Path, at_ms: int, max_width: int) -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (min(64, max_width), 64), (32, 64, 96)).save(out, "PNG")
        return out.getvalue()
