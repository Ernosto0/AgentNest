"""The only binary-dependent test; all other video tests remain offline/fake."""

import shutil
import subprocess

import pytest

from app.integrations.video.base import VideoProbeFailed
from app.integrations.video.ffmpeg import FfmpegVideoProber
from app.integrations.video.mp4_boxes import scan


@pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="ffmpeg and ffprobe are not installed",
)
def test_real_probe_thumbnail_and_upload(env, tmp_path, monkeypatch):
    settings = env.owner.client.app.state.settings.model_copy(update={"video_prober": "ffmpeg"})
    prober = FfmpegVideoProber(settings)
    path = tmp_path / "real.mp4"
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=360x640:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-t",
        "4",
        "-c:v",
        "libx264",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "2",
    ]
    subprocess.run(  # noqa: S603 - fixed lavfi fixtures, no untrusted input
        [*command, "-movflags", "+faststart", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    facts = prober.probe(path)
    assert 3900 <= facts.duration_ms <= 4300  # AAC priming can add a few ms
    assert (facts.width, facts.height) == (360, 640) and facts.video_codec == "h264"
    assert facts.moov_first and facts.audio_codecs == ("aac",)
    assert prober.extract_frame(path, 1000, 1080).startswith(b"\x89PNG")
    monkeypatch.setattr("app.content.router.get_video_prober", lambda settings: prober)
    with path.open("rb") as source:
        result = env.call(
            env.owner, "POST", "/media/video", files={"file": ("real.mp4", source, "video/mp4")}
        )
    assert result.status_code == 201, result.text
    assert result.json()["thumbnail_media_asset_id"] and result.json()["status"] == "ready"
    late = tmp_path / "late.mp4"
    subprocess.run(  # noqa: S603 - fixed lavfi fixtures, no untrusted input
        [*command, str(late)], check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=30
    )
    assert not scan(late).moov_first  # Verify the generated file, do not assume muxer behavior.
    with late.open("rb") as source:
        result = env.call(
            env.owner, "POST", "/media/video", files={"file": ("late.mp4", source, "video/mp4")}
        )
    assert result.status_code == 422 and result.json()["params"]["reason"] == "MOOV_NOT_AT_FRONT"
    for raw in (b"garbage", path.read_bytes()[:128]):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(raw)
        with pytest.raises(VideoProbeFailed):
            prober.probe(bad)
        result = env.call(
            env.owner, "POST", "/media/video", files={"file": ("bad.mp4", raw, "video/mp4")}
        )
        assert result.status_code == 422
