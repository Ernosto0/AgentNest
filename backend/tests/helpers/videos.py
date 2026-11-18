"""Offline fixtures: fake video files and tiny ISO BMFF box trees."""

import json
import struct
from typing import Any


def fake_video(**overrides: Any) -> bytes:
    return b"FAKEVIDEO1 " + json.dumps(overrides).encode() + b"\nopaque video payload"


def box(kind: bytes, payload: bytes = b"", *, extended: bool = False) -> bytes:
    if extended:
        return struct.pack(">I4sQ", 1, kind, len(payload) + 16) + payload
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def mp4(*, front: bool = True, brand: bytes = b"isom", edit: bool = False) -> bytes:
    ftyp = box(b"ftyp", brand + b"\0\0\0\0")
    moov = box(b"moov", box(b"trak", box(b"edts", box(b"elst"))) if edit else b"")
    mdat = box(b"mdat", b"opaque")
    return ftyp + (moov + mdat if front else mdat + moov)
