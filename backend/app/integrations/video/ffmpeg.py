"""Restricted ffmpeg 5.1 subprocess adapter (ADR-028). Never uses a shell."""

import json
import math
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.integrations.video.base import VideoFacts, VideoProbeFailed, VideoProbeUnavailable
from app.integrations.video.mp4_boxes import scan

PROBE_OUTPUT_BYTES = 1024 * 1024
THUMBNAIL_OUTPUT_BYTES = 16 * 1024 * 1024
ADDRESS_SPACE_BYTES = 2 * 1024**3
OPEN_FILES = 64
CORE_DUMP_BYTES = 0
CPU_GRACE_SECONDS = 5
BUSY_TIMEOUT_SECONDS = 3
RESOURCE_DIAGNOSTIC_BYTES = 4096
RESOURCE_FAILURE_MARKERS = (
    b"cannot allocate memory",
    b"out of memory",
    b"not enough memory",
    b"resource temporarily unavailable",
    b"too many open files",
    b"no space left on device",
    b"file too large",
)
# ffmpeg 5.1 accepts one alias, not the comma-separated format_name display value.
DEMUXER = "mov"
_semaphores: dict[int, threading.BoundedSemaphore] = {}
_lock = threading.Lock()


def _limits(timeout: int, output_limit: int) -> Callable[[], None] | None:
    if os.name != "posix":
        return None
    import importlib

    resource: Any = importlib.import_module("resource")

    def apply() -> None:
        for which, value in (
            (resource.RLIMIT_CPU, timeout + CPU_GRACE_SECONDS),
            (resource.RLIMIT_AS, ADDRESS_SPACE_BYTES),
            (resource.RLIMIT_FSIZE, output_limit),
            (resource.RLIMIT_NOFILE, OPEN_FILES),
            (resource.RLIMIT_CORE, CORE_DUMP_BYTES),
        ):
            resource.setrlimit(which, (value, value))

    return apply


def _number(value: Any, maximum: float = 1e15) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return result if math.isfinite(result) and 0 <= result <= maximum else 0


def _rate(value: Any) -> float:
    if not isinstance(value, str):
        return 0
    parts = value.split("/")
    if len(parts) == 2:
        denominator = _number(parts[1])
        return _number(parts[0]) / denominator if denominator else 0
    return _number(value)


def parse_facts(
    payload: Any, *, byte_size: int, major_brand: str, moov_first: bool, has_edit_list: bool
) -> VideoFacts:
    if not isinstance(payload, dict):
        raise VideoProbeFailed("CORRUPT_VIDEO")
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        raise VideoProbeFailed("CORRUPT_VIDEO")
    videos, audios = [], []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        disposition = stream.get("disposition") or {}
        if not isinstance(disposition, dict):
            disposition = {}
        if stream.get("codec_type") == "video" and disposition.get("attached_pic") != 1:
            videos.append(stream)
        elif stream.get("codec_type") == "audio":
            audios.append(stream)
    video = videos[0] if videos else {}
    fmt = payload.get("format") or {}
    if not isinstance(fmt, dict):
        fmt = {}
    duration = _number(video.get("duration")) or _number(fmt.get("duration"))
    width, height = (
        int(_number(video.get("width"), 100000)),
        int(_number(video.get("height"), 100000)),
    )
    tags = video.get("tags") or {}
    rotation = tags.get("rotate", 0) if isinstance(tags, dict) else 0
    side_data = video.get("side_data_list")
    if isinstance(side_data, list):
        for side in side_data:
            if isinstance(side, dict) and "rotation" in side:
                rotation = side["rotation"]
    try:
        angle = float(rotation)
        if not math.isfinite(angle):
            raise ValueError
        if abs(angle) % 180 == 90:
            width, height = height, width
    except (TypeError, ValueError, OverflowError):
        raise VideoProbeFailed("CORRUPT_VIDEO") from None
    bitrate = _number(video.get("bit_rate")) or _number(fmt.get("bit_rate"))
    if not bitrate and duration:
        bitrate = byte_size * 8 / duration
    return VideoFacts(
        container="mov" if major_brand == "qt  " else "mp4",
        major_brand=major_brand,
        duration_ms=round(duration * 1000),
        width=width,
        height=height,
        video_codec=str(video.get("codec_name", "")),
        pix_fmt=str(video.get("pix_fmt", "")),
        field_order=str(video.get("field_order", "unknown")),
        frame_rate=_rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate")),
        video_bitrate_bps=math.ceil(bitrate),
        audio_codecs=tuple(str(a.get("codec_name", "")) for a in audios),
        # A bad stream must not be hidden by a valid stream in the same file.
        audio_sample_rate=max(
            (int(_number(a.get("sample_rate"))) or 48001 for a in audios), default=0
        ),
        audio_channels=next(
            (
                int(_number(a.get("channels")))
                for a in audios
                if int(_number(a.get("channels"))) not in (1, 2)
            ),
            max((int(_number(a.get("channels"))) for a in audios), default=0),
        ),
        video_stream_count=len(videos),
        moov_first=moov_first,
        has_edit_list=has_edit_list,
    )


class FfmpegVideoProber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        with _lock:
            self.semaphore = _semaphores.setdefault(
                settings.video_probe_max_concurrency,
                threading.BoundedSemaphore(settings.video_probe_max_concurrency),
            )

    @contextmanager
    def _scratch(self) -> Iterator[Path]:
        try:
            with tempfile.TemporaryDirectory(
                dir=self.settings.media_scratch_dir or None
            ) as directory:
                yield Path(directory)
        except OSError as exc:
            raise VideoProbeUnavailable("scratch I/O unavailable") from exc

    def _run(self, binary: str, args: list[str], scratch: Path, timeout: int, cap: int) -> bytes:
        executable = shutil.which(binary)
        if executable is None:
            raise VideoProbeUnavailable("binary missing")
        if not self.semaphore.acquire(timeout=BUSY_TIMEOUT_SECONDS):
            raise VideoProbeUnavailable("busy")
        try:
            out, err = scratch / "stdout", scratch / "stderr"
            with out.open("wb") as stdout, err.open("wb") as stderr:
                try:
                    process = subprocess.Popen(  # noqa: S603 - fixed argument list, private local file only
                        [str(Path(executable).resolve()), *args],
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                        cwd=scratch,
                        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
                        start_new_session=os.name == "posix",
                        preexec_fn=_limits(timeout, cap),
                    )
                    try:
                        code = process.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)  # type: ignore[attr-defined]
                        else:
                            process.kill()
                        process.wait()
                        raise VideoProbeUnavailable("timeout") from None
                except OSError as exc:
                    raise VideoProbeUnavailable("cannot start probe") from exc
            if out.stat().st_size >= cap or err.stat().st_size >= cap or code < 0:
                raise VideoProbeUnavailable("resource limit")
            if code:
                with err.open("rb") as error_file:
                    diagnostic = error_file.read(RESOURCE_DIAGNOSTIC_BYTES).lower()
                if any(marker in diagnostic for marker in RESOURCE_FAILURE_MARKERS):
                    raise VideoProbeUnavailable("resource unavailable")
                raise VideoProbeFailed("CORRUPT_VIDEO")
            return out.read_bytes()
        except OSError as exc:
            raise VideoProbeUnavailable("scratch I/O unavailable") from exc
        finally:
            self.semaphore.release()

    def probe(self, path: Path) -> VideoFacts:
        boxes = scan(path)
        with self._scratch() as scratch:
            output = self._run(
                self.settings.video_ffprobe_path,
                [
                    "-v",
                    "error",
                    "-hide_banner",
                    "-protocol_whitelist",
                    "file",
                    "-f",
                    DEMUXER,
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-i",
                    str(path.resolve()),
                ],
                scratch,
                self.settings.video_probe_timeout_seconds,
                PROBE_OUTPUT_BYTES,
            )
        try:
            payload = json.loads(output)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise VideoProbeFailed("CORRUPT_VIDEO") from exc
        return parse_facts(
            payload,
            byte_size=path.stat().st_size,
            major_brand=boxes.major_brand,
            moov_first=boxes.moov_first,
            has_edit_list=boxes.has_edit_list,
        )

    def extract_frame(self, path: Path, at_ms: int, max_width: int) -> bytes:
        with self._scratch() as scratch:
            frame = scratch / "frame.png"
            for offset in (at_ms, 0):
                self._run(
                    self.settings.video_ffmpeg_path,
                    [
                        "-nostdin",
                        "-hide_banner",
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file",
                        "-f",
                        DEMUXER,
                        "-threads",
                        "1",
                        "-ss",
                        str(offset / 1000),
                        "-i",
                        str(path.resolve()),
                        "-map",
                        "0:V:0",
                        "-frames:v",
                        "1",
                        "-an",
                        "-sn",
                        "-dn",
                        "-vf",
                        f"scale='min({max_width},iw)':-2",
                        "-threads",
                        "1",
                        "-y",
                        str(frame),
                    ],
                    scratch,
                    self.settings.video_thumbnail_timeout_seconds,
                    THUMBNAIL_OUTPUT_BYTES,
                )
                if frame.exists() and frame.stat().st_size:
                    if frame.stat().st_size >= THUMBNAIL_OUTPUT_BYTES:
                        raise VideoProbeUnavailable("thumbnail limit")
                    return frame.read_bytes()
            raise VideoProbeFailed("CORRUPT_VIDEO")
