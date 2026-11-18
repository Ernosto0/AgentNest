"""Select the configured adapter."""

from app.core.config import Settings
from app.integrations.video.base import VideoProber
from app.integrations.video.fake import FakeVideoProber
from app.integrations.video.ffmpeg import FfmpegVideoProber


def get_video_prober(settings: Settings) -> VideoProber:
    if settings.video_prober == "fake":
        if settings.app_env == "production":
            raise ValueError("Fake video inspection is forbidden in production")
        return FakeVideoProber()
    return FfmpegVideoProber(settings)
