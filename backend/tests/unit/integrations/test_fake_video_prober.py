import io

import pytest
from PIL import Image

from app.integrations.video.base import VideoProbeFailed
from app.integrations.video.fake import FakeVideoProber
from tests.helpers.videos import fake_video


def test_fake_facts_and_frame(tmp_path):
    path = tmp_path / "video"
    path.write_bytes(fake_video(width=720, duration_ms=3000))
    prober = FakeVideoProber()
    assert prober.probe(path).width == 720
    assert prober.probe(path).duration_ms == 3000
    assert Image.open(io.BytesIO(prober.extract_frame(path, 0, 32))).width == 32
    assert prober.extract_frame(path, 0, 32) == prober.extract_frame(path, 0, 32)


def test_fake_refuses_non_video(tmp_path):
    path = tmp_path / "video"
    path.write_bytes(b"JPEG")
    with pytest.raises(VideoProbeFailed, match="NOT_A_VIDEO"):
        FakeVideoProber().probe(path)
