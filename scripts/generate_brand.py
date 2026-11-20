"""Rebuild Pivoris artwork from the supplied logo and bundled OFL Manrope font.

Dev tools only: pip install fonttools brotli pillow; install frontend's Playwright Chromium.
Run from any directory: python scripts/generate_brand.py
"""

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GREEN = "#253b31"
CREAM = "#edf5ec"
monogram = (
    ET.parse(ROOT / "logo.svg")
    .getroot()
    .find("{http://www.w3.org/2000/svg}path")
    .attrib["d"]
)
font = instantiateVariableFont(
    TTFont(ROOT / "frontend/src/assets/fonts/manrope-latin-wght-normal.woff2"),
    {"wght": 680},
)
glyphs = font.getGlyphSet()
pen = SVGPathPen(
    glyphs, ntos=lambda value: f"{value:.2f}".rstrip("0").rstrip(".") if value else "0"
)
cursor = 0
# Hand-set pairs in font units. Pull i/v and v/o into the diagonals' white space.
spacing = [-32, -38, -26, -18, -22, -18, 0]
for index, letter in enumerate("pivoris"):
    if letter == "i":
        # Keep the original stem; replace its square dot with a circular dot that
        # echoes the round caps of the official monogram. This is artwork, not a font.
        left, right = cursor + 160, cursor + 394.4
        pen.moveTo((left, 0))
        pen.lineTo((right, 0))
        pen.lineTo((right, -1080))
        pen.lineTo((left, -1080))
        pen.closePath()
        cx, cy, r = cursor + 277.2, -1355.2, 117.2
        k = r * 0.55228475
        pen.moveTo((cx + r, cy))
        pen.curveTo((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r))
        pen.curveTo((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy))
        pen.curveTo((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r))
        pen.curveTo((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))
        pen.closePath()
    elif letter == "v":
        # The signature detail: soften the existing v's vertex, keeping its
        # original top terminals, advance and diagonal weight. The i dots stay
        # unchanged; there is no second decorative motif.
        parse_path(
            "M40 1080H275.2L532 330Q550 278 568 330L824.4 1080H1060"
            "L680 58Q658 0 598 0H502Q442 0 420 58Z",
            TransformPen(pen, (1, 0, 0, -1, cursor, 0)),
        )
    else:
        glyphs[letter].draw(TransformPen(pen, (1, 0, 0, -1, cursor, 0)))
    cursor += glyphs[letter].width + spacing[index]

# Round, stable geometry with a tight bounding box; outlines avoid font-loading shifts.
bounds = BoundsPen(glyphs)
parse_path(pen.getCommands(), bounds)
x0, y0, x1, y1 = bounds.bounds
wordmark = pen.getCommands()
viewbox = f"{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}"
identity = {
    "monogram": monogram,
    "wordmark": wordmark,
    "wordmarkViewBox": viewbox,
    "wordmarkWidth": round(x1 - x0, 2),
    "wordmarkHeight": round(y1 - y0, 2),
}


def svg(body, box="0 0 90 90"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}">{body}</svg>\n'


def symbol(color=CREAM, transform="translate(-5 1.5)"):
    return f'<path d="{monogram}" transform="{transform}" fill="none" stroke="{color}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'


for app, component in [("frontend", "src/components"), ("landing", "src")]:
    base = ROOT / app
    target = base / component
    (target / "assets/brand").mkdir(parents=True, exist_ok=True)
    (target / "assets/brand/identity.json").write_text(
        json.dumps(identity, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    for name in ["Brand.tsx", "Brand.css"]:
        output = (
            "BrandIdentity.tsx" if app == "landing" and name == "Brand.tsx" else name
        )
        shutil.copyfile(ROOT / "scripts/brand" / name, target / output)
    public = base / "public"
    brand = public / "brand"
    brand.mkdir(exist_ok=True)
    for name, color in [("pivoris", GREEN), ("pivoris-reverse", CREAM)]:
        (brand / f"{name}-monogram.svg").write_text(
            svg(symbol(color)), encoding="utf-8"
        )
        (brand / f"{name}-wordmark.svg").write_text(
            svg(f'<path d="{wordmark}" fill="{color}"/>', viewbox), encoding="utf-8"
        )
    (public / "favicon.svg").write_text(
        svg(f'<rect width="90" height="90" rx="21" fill="{GREEN}"/>' + symbol()),
        encoding="utf-8",
    )
    # App icons are full bleed; operating systems supply their own corner masks.
    (brand / "icon-source.svg").write_text(
        svg(f'<rect width="90" height="90" fill="{GREEN}"/>' + symbol()),
        encoding="utf-8",
    )
    (brand / "maskable-source.svg").write_text(
        svg(
            f'<rect width="90" height="90" fill="{GREEN}"/>'
            + symbol(transform="translate(45 45) scale(.8) translate(-50 -43.5)")
        ),
        encoding="utf-8",
    )
    # Social artwork uses the exact same outlined wordmark; no product screenshots change.
    social = f'<rect width="1200" height="630" fill="#f7f8f3"/><rect x="64" y="64" width="1072" height="502" rx="24" fill="{GREEN}"/>'
    social += f'<g transform="translate(255 230) scale(1.85)">{symbol()}</g>'
    social += f'<g transform="translate(435 362) scale(.075)"><path d="{wordmark}" fill="{CREAM}"/></g>'
    social += '<path d="M288 432h624" stroke="#d1e4b7" stroke-width="2"/>'
    (brand / "social-source.svg").write_text(
        svg(social, "0 0 1200 630"), encoding="utf-8"
    )

subprocess.run(
    ["node", str(ROOT / "frontend/scripts/render-brand-assets.mjs")],
    cwd=ROOT,
    check=True,
)
for app in ["frontend", "landing"]:
    public = ROOT / app / "public"
    with Image.open(public / "app-icon-1024.png") as image:
        image.save(public / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("Generated both app identities, icons and social artwork.")
