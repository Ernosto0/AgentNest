"""Canned metadata and subprocess boundary tests; no binaries required."""

import json
import os
import subprocess

import pytest
from PIL import Image

from app.core.config import Settings
from app.integrations.video import ffmpeg
from app.integrations.video.base import VideoProbeUnavailable
from tests.helpers.videos import mp4


def payload(**video):
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
                **video,
            }
        ],
        "format": {"duration": "10"},
    }


def parse(data):
    return ffmpeg.parse_facts(
        data, byte_size=1000000, major_brand="isom", moov_first=True, has_edit_list=False
    )


def test_rotation_fallback_bitrate_and_silent():
    facts = parse(
        payload(side_data_list=[{"rotation": -90}], avg_frame_rate="0/0", r_frame_rate="30/1")
    )
    assert (facts.width, facts.height) == (1080, 1920)
    assert facts.frame_rate == 30 and facts.video_bitrate_bps == 800000
    assert facts.audio_codecs == ()
    assert parse(payload(tags={"rotate": "270"})).width == 1080


def test_stream_counts_and_audio_all_streams():
    data = payload()
    data["streams"] += [
        {"codec_type": "video", "disposition": {"attached_pic": 1}},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
        {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "96000", "channels": 3},
    ]
    facts = parse(data)
    assert facts.video_stream_count == 1
    assert facts.audio_codecs == ("aac", "mp3")
    assert facts.audio_sample_rate == 96000 and facts.audio_channels == 3
    data["streams"].append({"codec_type": "video"})
    assert parse(data).video_stream_count == 2


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"streams": [{}]},
        {"streams": [{"codec_type": "video", "width": [], "avg_frame_rate": "0/0"}]},
    ],
)
def test_missing_or_bad_optional_values(data):
    facts = parse(data)
    assert facts.duration_ms == 0 and facts.frame_rate == 0


def test_command_arguments_and_file_output(tmp_path, monkeypatch):
    path = tmp_path / "phone with spaces.mp4"
    path.write_bytes(mp4())
    calls = []

    class Process:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))
            kwargs["stdout"].write(json.dumps(payload()).encode())

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda value: value)
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", Process)
    facts = ffmpeg.FfmpegVideoProber(Settings()).probe(path)
    assert facts.width == 1920
    args, options = calls[0]
    assert isinstance(args, list) and "shell" not in options
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert args[args.index("-f") + 1] == ffmpeg.DEMUXER
    assert options["stdin"] == subprocess.DEVNULL
    assert set(options["env"]) == {"PATH", "LC_ALL"}
    assert options["stdout"].closed and options["stderr"].closed
    assert options["start_new_session"] == (os.name == "posix")
    assert (options["preexec_fn"] is not None) == (os.name == "posix")


def test_missing_binary_and_busy(tmp_path, monkeypatch):
    prober = ffmpeg.FfmpegVideoProber(Settings(video_probe_max_concurrency=1))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda value: None)
    with pytest.raises(VideoProbeUnavailable, match="binary missing"):
        prober._run("missing", [], tmp_path, 1, 1000)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda value: value)
    monkeypatch.setattr(ffmpeg, "BUSY_TIMEOUT_SECONDS", 0)
    prober.semaphore.acquire()
    try:
        with pytest.raises(VideoProbeUnavailable, match="busy"):
            prober._run("ffprobe", [], tmp_path, 1, 1000)
    finally:
        prober.semaphore.release()


def test_memory_allocation_failure_is_not_a_permanent_rejection(tmp_path, monkeypatch):
    class Process:
        def __init__(self, args, **kwargs):
            kwargs["stderr"].write(b"Cannot allocate memory")

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda value: value)
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", Process)
    with pytest.raises(VideoProbeUnavailable, match="resource unavailable"):
        ffmpeg.FfmpegVideoProber(Settings())._run("ffprobe", [], tmp_path, 1, 1000)


def test_timeout_kills_process_group(tmp_path, monkeypatch):
    killed = []

    class Process:
        pid = 123
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("probe", timeout)
            return -1

        def kill(self):
            killed.append("process")

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda value: value)
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", Process)
    if os.name == "posix":
        monkeypatch.setattr(ffmpeg.os, "killpg", lambda *args: killed.append("group"))
    with pytest.raises(VideoProbeUnavailable, match="timeout"):
        ffmpeg.FfmpegVideoProber(Settings())._run("ffprobe", [], tmp_path, 1, 1000)
    assert killed == ["group" if os.name == "posix" else "process"]


def test_thumbnail_command_and_empty_offset_fallback(tmp_path, monkeypatch):
    path = tmp_path / "phone.mp4"
    path.write_bytes(mp4())
    prober = ffmpeg.FfmpegVideoProber(Settings())
    calls = []

    def run(binary, args, scratch, timeout, cap):
        calls.append(args)
        assert args[args.index("-protocol_whitelist") + 1] == "file"
        assert args[args.index("-f") + 1] == ffmpeg.DEMUXER
        assert args[args.index("-map") + 1] == "0:V:0"
        assert "-nostdin" in args and cap == ffmpeg.THUMBNAIL_OUTPUT_BYTES
        if len(calls) == 2:
            Image.new("RGB", (32, 64)).save(scratch / "frame.png")
        return b""

    monkeypatch.setattr(prober, "_run", run)
    assert prober.extract_frame(path, 1000, 1080).startswith(b"\x89PNG")
    assert [args[args.index("-ss") + 1] for args in calls] == ["1.0", "0.0"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource limits; Windows relies on timeout")
def test_resource_limits(monkeypatch):
    import resource

    calls = []
    monkeypatch.setattr(resource, "setrlimit", lambda *args: calls.append(args))
    ffmpeg._limits(30, ffmpeg.PROBE_OUTPUT_BYTES)()
    assert len(calls) == 5
    assert (resource.RLIMIT_CORE, (0, 0)) in calls
