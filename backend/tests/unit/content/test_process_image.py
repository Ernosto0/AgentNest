"""P5-01 / plan.md G12: the deterministic image pipeline (no database, no storage)."""

import hashlib
import io

import pytest
from PIL import Image, ImageCms

from app.content import media
from app.content.media import MediaRejected, process_image, sanitize_filename
from tests.helpers.images import jpeg_with_exif, png_bytes


def reopen(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_a_png_becomes_a_baseline_rgb_jpeg() -> None:
    result = process_image(png_bytes((120, 80)))
    image = reopen(result.data)
    assert image.format == "JPEG"
    assert image.mode == "RGB"
    assert (result.width, result.height) == (120, 80) == image.size
    assert "progressive" not in image.info and "progression" not in image.info
    assert len(result.sha256) == 64


def test_the_hash_is_over_the_output_not_the_input() -> None:
    raw = png_bytes()
    result = process_image(raw)
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()
    assert result.sha256 != hashlib.sha256(raw).hexdigest()


def test_processing_is_deterministic() -> None:
    raw = png_bytes((64, 64))
    assert process_image(raw) == process_image(raw)


def test_exif_and_gps_are_stripped_and_the_orientation_is_applied() -> None:
    source = jpeg_with_exif((200, 100), orientation=6)
    assert reopen(source).getexif().get(0x010F) == "SecretCam"  # the fixture really has EXIF
    result = process_image(source)
    image = reopen(result.data)
    assert len(image.getexif()) == 0
    assert b"Exif" not in result.data and b"SecretCam" not in result.data
    assert "icc_profile" not in image.info
    # Orientation 6 means "rotate for display": 200x100 becomes 100x200 and stays upright.
    assert (result.width, result.height) == (100, 200)


def test_a_jpeg_without_exif_is_reencoded_too() -> None:
    out = io.BytesIO()
    Image.new("RGB", (50, 50), "green").save(out, "JPEG", quality=30)
    result = process_image(out.getvalue())
    assert result.data != out.getvalue()
    assert reopen(result.data).format == "JPEG"


def test_an_embedded_profile_does_not_reach_the_output() -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    out = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(out, "PNG", icc_profile=profile)
    assert reopen(out.getvalue()).info.get("icc_profile")
    result = process_image(out.getvalue())
    assert "icc_profile" not in reopen(result.data).info


@pytest.mark.parametrize(
    ("mode", "color"),
    [("RGBA", (255, 0, 0, 128)), ("LA", (200, 128)), ("L", 90), ("P", 3), ("1", 1)],
)
def test_other_color_modes_become_rgb(mode: str, color: object) -> None:
    result = process_image(png_bytes((30, 30), mode=mode, color=color))
    assert reopen(result.data).mode == "RGB"


def test_transparency_is_flattened_onto_white() -> None:
    result = process_image(png_bytes((20, 20), mode="RGBA", color=(255, 0, 0, 0)))
    pixel = reopen(result.data).getpixel((10, 10))
    assert isinstance(pixel, tuple) and min(pixel) > 240


def test_a_cmyk_jpeg_is_converted_to_rgb() -> None:
    out = io.BytesIO()
    Image.new("CMYK", (30, 30), (0, 255, 255, 0)).save(out, "JPEG")
    assert reopen(process_image(out.getvalue()).data).mode == "RGB"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"", media.REASON_EMPTY),
        (b"just some text, not an image\n", media.REASON_NOT_AN_IMAGE),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", media.REASON_NOT_AN_IMAGE),
        (b"%PDF-1.7\n1 0 obj\n", media.REASON_NOT_AN_IMAGE),
    ],
)
def test_non_images_are_rejected(raw: bytes, reason: str) -> None:
    with pytest.raises(MediaRejected) as caught:
        process_image(raw)
    assert caught.value.reason == reason


def test_a_gif_is_not_accepted() -> None:
    out = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(out, "GIF")
    with pytest.raises(MediaRejected) as caught:
        process_image(out.getvalue())
    assert caught.value.reason == media.REASON_NOT_AN_IMAGE


def test_a_truncated_image_is_rejected_as_corrupt() -> None:
    raw = png_bytes((300, 300))
    with pytest.raises(MediaRejected) as caught:
        process_image(raw[: len(raw) // 2])
    assert caught.value.reason == media.REASON_CORRUPT


def test_an_image_over_the_pixel_cap_is_rejected_before_decoding() -> None:
    # ~49 megapixels, but a few dozen KB as a PNG: the classic decompression bomb.
    raw = png_bytes((7000, 7000), mode="L", color=0)
    assert len(raw) < 200_000
    with pytest.raises(MediaRejected) as caught:
        process_image(raw)
    assert caught.value.reason == media.REASON_TOO_MANY_PIXELS


def test_a_pillow_decompression_bomb_warning_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 6000)  # 100x100 = 10000: a warning, not error
    with pytest.raises(MediaRejected) as caught:
        process_image(png_bytes((100, 100)))
    assert caught.value.reason == media.REASON_TOO_MANY_PIXELS


def test_the_pixel_cap_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "MAX_IMAGE_PIXELS", 100 * 50)
    assert process_image(png_bytes((100, 50))).width == 100
    with pytest.raises(MediaRejected):
        process_image(png_bytes((101, 50)))


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (None, None),
        ("", None),
        ("photo.png", "photo.png"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\kapak fotoğrafı.jpg", "kapak fotoğrafı.jpg"),
        ("bad\x00name\n.png", "badname.png"),
        ("a/", None),
        ("x" * 500, "x" * 120),
    ],
)
def test_filenames_are_sanitised_for_display(given: str | None, expected: str | None) -> None:
    assert sanitize_filename(given) == expected
