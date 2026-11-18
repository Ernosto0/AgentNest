"""Bounded ISO BMFF inspection without reading video payloads."""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.integrations.video.base import VideoProbeFailed, VideoProbeUnavailable

MAX_TOP_LEVEL_BOXES = 256
MAX_NESTED_BOXES = 4096
MAX_MOOV_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 4
MP4_BRANDS = {
    b"isom",
    b"iso2",
    b"iso3",
    b"iso4",
    b"iso5",
    b"iso6",
    b"mp41",
    b"mp42",
    b"avc1",
    b"M4V ",
    b"MSNV",
    b"dash",
}


@dataclass(frozen=True)
class BoxFacts:
    major_brand: str
    box_types: tuple[str, ...]
    moov_first: bool
    has_edit_list: bool


def _boxes(file: BinaryIO, start: int, end: int, cap: int) -> list[tuple[bytes, int, int]]:
    result: list[tuple[bytes, int, int]] = []
    cursor = start
    while cursor < end:
        if len(result) >= cap or end - cursor < 8:
            raise VideoProbeFailed("CORRUPT_VIDEO")
        file.seek(cursor)
        header = file.read(8)
        if len(header) != 8:
            raise VideoProbeFailed("CORRUPT_VIDEO")
        size, kind = struct.unpack(">I4s", header)
        head_size = 8
        if size == 1:
            extended = file.read(8)
            if len(extended) != 8:
                raise VideoProbeFailed("CORRUPT_VIDEO")
            size = struct.unpack(">Q", extended)[0]
            head_size = 16
        elif size == 0:
            size = end - cursor
        if size < head_size or size > end - cursor:
            raise VideoProbeFailed("CORRUPT_VIDEO")
        result.append((kind, cursor + head_size, cursor + size))
        cursor += size
    return result


def scan(path: Path) -> BoxFacts:
    size = path.stat().st_size
    if size == 0:
        raise VideoProbeFailed("EMPTY_FILE")
    with path.open("rb") as file:
        header = file.read(8)
        if len(header) < 8 or any(c < 32 or c > 126 for c in header[4:8]):
            raise VideoProbeFailed("NOT_A_VIDEO")
        boxes = _boxes(file, 0, size, MAX_TOP_LEVEL_BOXES)
        ftyp = next((b for b in boxes if b[0] == b"ftyp"), None)
        if ftyp is None:
            raise VideoProbeFailed("NOT_A_VIDEO")
        if ftyp[2] - ftyp[1] < 8:
            raise VideoProbeFailed("CORRUPT_VIDEO")
        file.seek(ftyp[1])
        brand = file.read(4)
        if brand != b"qt  " and brand not in MP4_BRANDS:
            raise VideoProbeFailed("UNSUPPORTED_CONTAINER")
        moov = next((b for b in boxes if b[0] == b"moov"), None)
        if moov is None:
            raise VideoProbeFailed("CORRUPT_VIDEO")
        if moov[2] - moov[1] > MAX_MOOV_BYTES:
            raise VideoProbeUnavailable("moov inspection limit")
        budget = [MAX_NESTED_BOXES]

        def edit_list(start: int, end: int, depth: int = 0) -> bool:
            if depth >= MAX_DEPTH:
                raise VideoProbeFailed("CORRUPT_VIDEO")
            children = _boxes(file, start, end, budget[0])
            budget[0] -= len(children)
            expected = (b"trak", b"edts", b"elst")[depth]
            for kind, left, right in children:
                if kind == expected and (kind == b"elst" or edit_list(left, right, depth + 1)):
                    return True
            return False

        order = tuple(b[0].decode("latin1") for b in boxes)
        first = next((x for x in order if x in ("moov", "mdat")), None)
        return BoxFacts(brand.decode("latin1"), order, first == "moov", edit_list(moov[1], moov[2]))
