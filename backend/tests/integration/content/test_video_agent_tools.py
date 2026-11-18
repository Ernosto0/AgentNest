import pytest

from tests.integration.content.test_agent_content_tools import arm, tool


@pytest.mark.parametrize("kind", ["video", "video_thumbnail"])
def test_agent_media_listing_and_prepare_refuse_non_images(pub, kind):
    ctx = arm(pub)
    media = pub.media()
    media.kind = kind
    if kind == "video":
        media.duration_ms, media.frame_rate = 10000, 30
        media.video_codec, media.container = "h264", "mp4"
    pub.session.commit()
    result = tool(pub, ctx, "content.read", kind="media", limit=10, cursor=None)
    assert str(media.id) not in str(result)
    result = tool(
        pub,
        ctx,
        "content.prepare",
        content_type="feed_image",
        title="Image",
        media_asset_id=str(media.id),
        caption={"template": "Merhaba", "language": "tr"},
    )
    assert result["status"] == "refused" and result["reason"] == "MEDIA_KIND_INVALID"
