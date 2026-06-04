#!/usr/bin/env python3
"""Generate seller favicon raster assets from source-of-truth SVG (Phase 168)."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "seller_console" / "static"
SVG_PATH = STATIC_DIR / "favicon.svg"
APPLE_PATH = STATIC_DIR / "apple-touch-icon.png"
ICON_192_PATH = STATIC_DIR / "icon-192.png"
ICON_512_PATH = STATIC_DIR / "icon-512.png"
ICO_PATH = STATIC_DIR / "favicon.ico"


def _png_from_svg(svg_text: str, size: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=size, output_height=size)
    return Image.open(BytesIO(png_bytes)).convert("RGBA")


def _small_svg_variant(svg_text: str) -> str:
    small = re.sub(r"<filter id=\"glow\">.*?</filter>", "", svg_text, flags=re.DOTALL)
    small = re.sub(r"<filter id=\"sg\">.*?</filter>", "", small, flags=re.DOTALL)
    small = re.sub(r"\s*<g filter=\"url\(#sg\)\">.*?</g>\s*</svg>", "\n</svg>", small, flags=re.DOTALL)
    small = small.replace(' filter="url(#glow)"', "")
    # v9: orbit stroke-width is 20 — keep slightly reduced for small sizes
    small = small.replace('stroke-width="20"', 'stroke-width="16"')
    small = small.replace('stroke-width="16"', 'stroke-width="12"')
    small = small.replace('stroke-width="12"', 'stroke-width="10"')
    small = small.replace('r="14"', 'r="10"')
    return small


def main() -> None:
    svg_text = SVG_PATH.read_text(encoding="utf-8")

    _png_from_svg(svg_text, 512).save(ICON_512_PATH)
    _png_from_svg(svg_text, 192).save(ICON_192_PATH)
    _png_from_svg(svg_text, 180).save(APPLE_PATH)

    small_svg = _small_svg_variant(svg_text)
    ico_base = _png_from_svg(small_svg, 48)
    ico_base.save(ICO_PATH, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    print(f"Generated: {ICO_PATH.name}, {APPLE_PATH.name}, {ICON_192_PATH.name}, {ICON_512_PATH.name}")


if __name__ == "__main__":
    main()
