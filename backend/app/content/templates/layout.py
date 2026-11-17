"""Integer pixel text layout, greedy wrap, bounded shrink and ellipsis."""

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

FONTS = Path(__file__).parent / "fonts"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    weight = "Bold" if bold else "Regular"
    return ImageFont.truetype(
        str(FONTS / f"NotoSans-{weight}.ttf"), size, layout_engine=ImageFont.Layout.BASIC
    )


def wrap(text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if face.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and face.getlength(line + char) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


@dataclass(frozen=True)
class TextBox:
    bounds: tuple[int, int, int, int]
    lines: tuple[str, ...]
    size: int
    bold: bool
    highlight: bool = False


def fit(
    text: str,
    bounds: tuple[int, int, int, int],
    *,
    size: int = 64,
    minimum: int = 28,
    max_lines: int = 4,
    bold: bool = False,
    highlight: bool = False,
) -> TextBox:
    x, y, right, bottom = bounds
    for current in range(size, minimum - 1, -2):
        face = font(current, bold)
        lines = wrap(text, face, right - x)
        capacity = min(max_lines, (bottom - y) // (current * 3 // 2))
        if len(lines) <= capacity:
            return TextBox(bounds, tuple(lines), current, bold, highlight)
    current = minimum
    face = font(current, bold)
    lines = wrap(text, face, right - x)
    capacity = max(1, min(max_lines, (bottom - y) // (current * 3 // 2)))
    if len(lines) > capacity:
        lines = lines[:capacity]
        last = lines[-1].rstrip()
        while last and face.getlength(last + "…") > right - x:
            last = last[:-1]
        lines[-1] = last + "…"
    return TextBox(bounds, tuple(lines), current, bold, highlight)
