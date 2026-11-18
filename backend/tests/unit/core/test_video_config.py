from app.content.video import MAX_VIDEO_BYTES
from app.core.config import Settings


def test_video_defaults_and_fake_production_refusal():
    cfg = Settings(_env_file=None, video_prober="ffmpeg")
    assert cfg.video_probe_timeout_seconds == 30
    assert cfg.media_max_video_bytes == MAX_VIDEO_BYTES
    assert cfg.media_video_workspace_quota_bytes == 2 * 1024**3
    cfg = cfg.model_copy(update={"app_env": "production", "video_prober": "fake"})
    assert "VIDEO_PROBER must not be fake in production." in cfg.safety_problems()
