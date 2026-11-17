"""Pure deterministic card rendering. No database, storage, time or system fonts."""

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps

from app.content.templates.layout import TextBox, fit, font
from app.content.templates.spec import SIZES, BrandRecord, CardFormat

LOGO_BOX = (760, 270, 984, 390)


@dataclass(frozen=True)
class ResolvedCard:
    template: str
    format: CardFormat
    title: str
    rows: tuple[str, ...]
    footer: str


def contrast(color: str) -> str:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    luminance = sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))
    # Choose whichever has the higher WCAG contrast (always >= 4.58:1).
    return "#000000" if luminance > 0.179 else "#ffffff"


def layout(card: ResolvedCard) -> tuple[TextBox, ...]:
    _, height = SIZES[card.format]
    bottom = height - (340 if card.format == "story" else 90)
    title = fit(card.title, (96, 420, 984, 660), size=82, max_lines=2, bold=True)
    boxes = [title]
    count = max(1, len(card.rows))
    row_height = (bottom - 120 - 690) // count
    for index, row in enumerate(card.rows):
        y = 690 + index * row_height
        boxes.append(
            fit(
                row,
                (112, y, 968, y + row_height - 16),
                size=64 if count == 1 else 42,
                max_lines=8 if count == 1 else 2,
                highlight=card.template == "price_card",
            )
        )
    boxes.append(fit(card.footer, (96, bottom - 72, 984, bottom), size=32, max_lines=1))
    return tuple(boxes)


def render_card(
    card: ResolvedCard, brand: BrandRecord, logo_image: Image.Image | None = None
) -> bytes:
    image = Image.new("RGB", SIZES[card.format], brand.primary_color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((96, 270, 320, 286), fill=brand.accent_color)
    if logo_image is not None:
        logo = ImageOps.contain(logo_image.convert("RGBA"), (224, 120), Image.Resampling.LANCZOS)
        image.paste(logo, (LOGO_BOX[0] + (224 - logo.width) // 2, LOGO_BOX[1]), logo)
    for box in layout(card):
        x, y, right, bottom = box.bounds
        background = brand.accent_color if box.highlight else brand.primary_color
        if box.highlight:
            pill_bottom = min(bottom, y + len(box.lines) * (box.size * 3 // 2) + 24)
            draw.rounded_rectangle(
                (x - 16, y - 8, right + 16, pill_bottom), radius=24, fill=background
            )
        face = font(box.size, box.bold)
        for index, line in enumerate(box.lines):
            draw.text(
                (x, y + index * (box.size * 3 // 2)),
                line,
                font=face,
                fill=contrast(background),
                anchor="lt",
            )
    out = io.BytesIO()
    image.save(out, "PNG", optimize=False, compress_level=9)
    return out.getvalue()
