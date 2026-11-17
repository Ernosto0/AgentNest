"""Determinism/layout and tolerant goldens. Regenerate with:
uv run python -m tests.unit.content.templates.regen_goldens
Review changed thumbnails; never compare full pixel hashes between platforms.
"""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from pydantic import TypeAdapter, ValidationError

from app.content.templates.cards import LOGO_BOX, contrast, layout, render_card
from app.content.templates.layout import fit, font, wrap
from app.content.templates.spec import LABELS, SIZES, Announcement, TemplateInput
from tests.unit.content.templates.samples import BRAND, sample


@pytest.mark.parametrize("template", LABELS)
@pytest.mark.parametrize("fmt", SIZES)
def test_dimensions_determinism_layout_and_golden(template, fmt):
    card = sample(template, fmt)
    first = render_card(card, BRAND)
    assert first == render_card(card, BRAND)
    image = Image.open(io.BytesIO(first))
    assert image.size == SIZES[fmt]
    assert image.mode == "RGB"
    logo = Image.new("RGBA", (400, 150), "white")
    assert render_card(card, BRAND, logo) == render_card(card, BRAND, logo)
    for box in layout(card):
        x, y, right, bottom = box.bounds
        assert 0 <= x < right <= image.width
        assert 0 <= y < bottom <= image.height
        if fmt == "story":
            assert y >= 250 and bottom <= image.height - 340
        lx, ly, lr, lb = LOGO_BOX
        assert right <= lx or x >= lr or bottom <= ly or y >= lb
        face = font(box.size, box.bold)
        assert all(face.getlength(line) <= right - x for line in box.lines)
        assert len(box.lines) * (box.size * 3 // 2) <= bottom - y
    thumb = image.convert("L").resize((108, image.height // 10), Image.Resampling.LANCZOS)
    golden = Image.open(Path(__file__).parent / "goldens" / f"{template}-{fmt}.png")
    assert ImageStat.Stat(ImageChops.difference(thumb, golden)).mean[0] < 3.0


def test_long_turkish_and_single_word_are_bounded():
    box = fit("Çığ gibi büyüyen ışığımız " * 100, (0, 0, 400, 200), max_lines=2)
    assert len(box.lines) == 2
    assert box.lines[-1].endswith("…")
    lines = wrap("ğ" * 100, font(40), 150)
    assert len(lines) > 1
    assert "".join(lines) == "ğ" * 100
    assert all(font(40).getlength(line) <= 150 for line in lines)


@pytest.mark.parametrize("bold", [False, True])
def test_turkish_glyphs_and_case_survive(bold):
    face = font(42, bold)
    tofu = bytes(face.getmask("\U0010ffff"))
    for char in "ğĞıİşŞçÇöÖüÜ₺–":
        mask = face.getmask(char)
        assert mask.getbbox() is not None
        assert bytes(mask) != tofu
    body = Announcement(template="announcement", format="story", headline="İ\u0000 ı", body="şçöü")
    assert body.headline == "İ ı"
    card = sample("announcement", "story")
    assert any("ğĞıİşŞçÇöÖüÜ ₺" in line for box in layout(card) for line in box.lines)


def test_contrast_selects_black_or_white():
    assert contrast("#ffffff") == "#000000"
    assert contrast("#000000") == "#ffffff"


@pytest.mark.parametrize("extra", [{"price": 10}, {"fact_key": "BAD KEY"}, {"language": "de"}])
def test_strict_inputs(extra):
    with pytest.raises(ValidationError):
        TypeAdapter(TemplateInput).validate_python(
            {"template": "price_card", "format": "feed", "fact_key": "pricing.monthly", **extra}
        )
