"""Checks on a downloaded voice note: declared type, file signature and duration.

The webhook does not say how long a voice note is, so the duration is read from the container
when it is an MP4/M4A (the usual Instagram voice-note container, unverified against a live
account) or a WAV. For other containers the duration is unknown here and the byte cap is the
bound. Nothing here decodes audio.
"""

import json
import struct

FAKE_MAGIC = b"AGENTNEST-FAKE-AUDIO\n"

# Declared content types accepted from the CDN (parameters such as ``; codecs=`` are ignored).
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "video/mp4": "mp4",  # some CDNs label an audio-only MP4 as video
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/flac": "flac",
}
# A CDN that does not know the type: the file signature decides.
GENERIC_CONTENT_TYPES = frozenset({"application/octet-stream", "binary/octet-stream"})


def media_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def declared_type_allowed(content_type: str | None) -> bool:
    kind = media_type(content_type)
    return kind in ALLOWED_CONTENT_TYPES or kind in GENERIC_CONTENT_TYPES


def sniff_extension(data: bytes) -> str | None:
    """The container by its file signature, or ``None`` when it is not a supported audio."""
    if data.startswith(FAKE_MAGIC):
        return "m4a"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "m4a"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if data.startswith(b"OggS"):
        return "ogg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if data.startswith(b"fLaC"):
        return "flac"
    return None


def extension_for(content_type: str | None, data: bytes) -> str | None:
    """The file extension to send to a provider, or ``None`` when the clip is not supported
    (a declared type that disagrees with the signature is refused)."""
    sniffed = sniff_extension(data)
    if sniffed is None:
        return None
    declared = ALLOWED_CONTENT_TYPES.get(media_type(content_type))
    if declared is not None and {declared, sniffed} <= {"m4a", "mp4"}:
        return declared
    if declared is not None and declared != sniffed:
        return None
    return sniffed


# --- duration -------------------------------------------------------------------------------


def _mp4_duration(data: bytes) -> float | None:
    def boxes(start: int, end: int):  # type: ignore[no-untyped-def]
        pos = start
        while pos + 8 <= end:
            size, kind = struct.unpack(">I4s", data[pos : pos + 8])
            header = 8
            if size == 1:
                if pos + 16 > end:
                    return
                size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                return
            yield kind, pos + header, pos + size
            pos += size

    for kind, body, stop in boxes(0, len(data)):
        if kind != b"moov":
            continue
        for inner, inner_body, inner_stop in boxes(body, stop):
            if inner != b"mvhd" or inner_body + 4 > inner_stop:
                continue
            version = data[inner_body]
            try:
                if version == 1:
                    timescale, duration = struct.unpack(
                        ">IQ", data[inner_body + 20 : inner_body + 32]
                    )
                else:
                    timescale, duration = struct.unpack(
                        ">II", data[inner_body + 12 : inner_body + 20]
                    )
            except struct.error:
                return None
            return duration / timescale if timescale else None
    return None


def _wav_duration(data: bytes) -> float | None:
    byte_rate: int | None = None
    pos = 12
    while pos + 8 <= len(data):
        chunk, size = struct.unpack("<4sI", data[pos : pos + 8])
        if chunk == b"fmt " and pos + 8 + 12 <= len(data):
            byte_rate = struct.unpack("<I", data[pos + 16 : pos + 20])[0]
        elif chunk == b"data":
            return size / byte_rate if byte_rate else None
        pos += 8 + size + (size & 1)
    return None


def _fake_duration(data: bytes) -> float | None:
    try:
        meta = json.loads(data[len(FAKE_MAGIC) :].decode("utf-8"))
        value = meta.get("duration")
        return float(value) if isinstance(value, int | float) else None
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def probe_duration_seconds(data: bytes) -> float | None:
    """The clip's duration in seconds, or ``None`` when the container does not say."""
    if data.startswith(FAKE_MAGIC):
        return _fake_duration(data)
    kind = sniff_extension(data)
    if kind in ("m4a", "mp4"):
        return _mp4_duration(data)
    if kind == "wav":
        return _wav_duration(data)
    return None
