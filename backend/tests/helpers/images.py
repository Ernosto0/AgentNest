"""Build small images in memory for the media tests."""

import io
from typing import Any

from PIL import Image


def png_bytes(size: tuple[int, int] = (120, 80), mode: str = "RGB", color: Any = "tomato") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, "PNG")
    return out.getvalue()


def jpeg_with_exif(size: tuple[int, int] = (200, 100), orientation: int = 6) -> bytes:
    """A JPEG that carries an orientation, a camera name and GPS coordinates."""
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "SecretCam"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (41.0, 1.0, 2.0)
    gps[3] = "E"
    gps[4] = (29.0, 3.0, 4.0)
    out = io.BytesIO()
    Image.new("RGB", size, "navy").save(out, "JPEG", exif=exif)
    return out.getvalue()
