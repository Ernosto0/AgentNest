"""Checks on a downloaded image: declared type and file signature.

Only JPEG, PNG and WebP are sent to the model (what the provider accepts; an animated GIF is
refused). The signature decides what the file is; a declared type that disagrees is refused. Nothing
here decodes the image, so a decompression bomb cannot happen here: the byte cap bounds the upload
and the provider does the decoding.
"""

FAKE_IMAGE_MAGIC = b"\x89PNG\r\n\x1a\nPIVORIS-FAKE-IMAGE\n"

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
SUPPORTED_MEDIA_TYPES = (JPEG, PNG, WEBP)

_DECLARED = {
    "image/jpeg": JPEG,
    "image/jpg": JPEG,
    "image/pjpeg": JPEG,
    "image/png": PNG,
    "image/webp": WEBP,
}
# A CDN that does not know the type: the file signature decides.
GENERIC_CONTENT_TYPES = frozenset({"application/octet-stream", "binary/octet-stream"})


def media_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def declared_type_allowed(content_type: str | None) -> bool:
    kind = media_type(content_type)
    return kind in _DECLARED or kind in GENERIC_CONTENT_TYPES


def sniff_media_type(data: bytes) -> str | None:
    """The image type by its file signature, or ``None`` when it is not a supported image."""
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    return None


def resolved_media_type(content_type: str | None, data: bytes) -> str | None:
    """The media type to send to the model, or ``None`` when the file is not a supported image
    (or its declared type disagrees with its signature)."""
    sniffed = sniff_media_type(data)
    if sniffed is None:
        return None
    declared = _DECLARED.get(media_type(content_type))
    if declared is not None and declared != sniffed:
        return None
    return sniffed
