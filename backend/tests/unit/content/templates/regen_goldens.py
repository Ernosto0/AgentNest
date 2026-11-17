"""Run from backend: uv run python -m tests.unit.content.templates.regen_goldens."""

import io
from pathlib import Path

from PIL import Image

from app.content.templates.cards import render_card
from app.content.templates.spec import LABELS, SIZES
from tests.unit.content.templates.samples import BRAND, sample

if __name__ == "__main__":
    folder = Path(__file__).parent / "goldens"
    folder.mkdir(exist_ok=True)
    for template in LABELS:
        for fmt, size in SIZES.items():
            image = Image.open(io.BytesIO(render_card(sample(template, fmt), BRAND)))
            image.convert("L").resize((108, size[1] // 10), Image.Resampling.LANCZOS).save(
                folder / f"{template}-{fmt}.png"
            )
