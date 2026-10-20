"""G19: the committed demo images are valid uploads of the documented size."""

from pathlib import Path

import pytest

from app.content.media import process_image

DEMO_MEDIA = Path(__file__).resolve().parents[3] / "app" / "demo" / "media"


@pytest.mark.parametrize(
    ("name", "size"),
    [("story-sample.png", (1080, 1920)), ("feed-sample.jpg", (1080, 1350))],
)
def test_the_demo_images_are_accepted_uploads(name: str, size: tuple[int, int]) -> None:
    result = process_image((DEMO_MEDIA / name).read_bytes())
    assert (result.width, result.height) == size
