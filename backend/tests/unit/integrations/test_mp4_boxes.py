import struct

import pytest

from app.integrations.video.base import VideoProbeFailed
from app.integrations.video.mp4_boxes import scan
from tests.helpers.videos import box, mp4


@pytest.mark.parametrize(
    ("front", "edit", "brand"), [(True, False, b"isom"), (False, True, b"qt  ")]
)
def test_order_brand_edit_list(tmp_path, front, edit, brand):
    path = tmp_path / "video"
    path.write_bytes(mp4(front=front, edit=edit, brand=brand))
    facts = scan(path)
    assert facts.moov_first == front
    assert facts.has_edit_list == edit
    assert facts.major_brand == brand.decode()


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"", "EMPTY_FILE"),
        (box(b"free"), "NOT_A_VIDEO"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "NOT_A_VIDEO"),
        (mp4(brand=b"3gp6"), "UNSUPPORTED_CONTAINER"),
        (mp4(brand=b"M4A "), "UNSUPPORTED_CONTAINER"),
        (mp4(brand=b"mjp2"), "UNSUPPORTED_CONTAINER"),
        (mp4()[:-1], "CORRUPT_VIDEO"),
        (struct.pack(">I4s", 1000000, b"ftyp"), "CORRUPT_VIDEO"),
        (box(b"ftyp", b"isom"), "CORRUPT_VIDEO"),
        (struct.pack(">I4s", 1, b"ftyp"), "CORRUPT_VIDEO"),
    ],
)
def test_bad_boxes(tmp_path, raw, reason):
    path = tmp_path / "video"
    path.write_bytes(raw)
    with pytest.raises(VideoProbeFailed) as caught:
        scan(path)
    assert caught.value.reason == reason


def test_extended_and_to_eof_sizes(tmp_path):
    path = tmp_path / "video"
    path.write_bytes(
        box(b"ftyp", b"isom\0\0\0\0", extended=True)
        + box(b"moov", extended=True)
        + struct.pack(">I4s", 0, b"mdat")
        + b"payload"
    )
    assert scan(path).moov_first
