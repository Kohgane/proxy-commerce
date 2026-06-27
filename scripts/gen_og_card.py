#!/usr/bin/env python3
"""v28: 공유 카드(OG) 이미지 생성 — 1200×630, 먹 vault + 브릿지 마크 + GOGA BRIDJ 워드마크.

소스 = assets/brand-icons/icon-master-1024.png(확정 브릿지 마크). 옛 글러브 폐기.
폰트는 생성 시점에만 필요(산출 PNG는 커밋됨). 누락 시 기본 폰트로 폴백.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "assets" / "brand-icons" / "icon-master-1024.png"
OUT_STATIC = ROOT / "src" / "seller_console" / "static" / "og-card.png"
OUT_VENDOR = ROOT / "assets" / "og" / "og-card-1200x630.png"

W, H = 1200, 630
INK = (26, 23, 20, 255)        # #1A1714
GOLD = (201, 162, 75, 255)     # #C9A24B
CREAM = (245, 239, 227, 255)   # #F5EFE3

_SERIF_CANDIDATES = [
    "/mnt/skills/examples/canvas-design/canvas-fonts/IBMPlexSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]


def _font(size: int):
    for p in _SERIF_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _text_spaced(d: ImageDraw.ImageDraw, xy, text, font, fill, tracking=0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        w = d.textlength(ch, font=font)
        x += w + tracking
    return x


def main() -> None:
    OUT_VENDOR.parent.mkdir(parents=True, exist_ok=True)
    card = Image.new("RGBA", (W, H), INK)
    d = ImageDraw.Draw(card)

    # 금 헤어라인 보더(절제된 프리미엄)
    d.rounded_rectangle([18, 18, W - 19, H - 19], radius=28, outline=(201, 162, 75, 90), width=2)

    # 브릿지 마크 — 좌측 중앙
    mark = Image.open(MASTER).convert("RGBA").resize((430, 430), Image.LANCZOS)
    card.alpha_composite(mark, (96, (H - 430) // 2))

    # 워드마크 GOGA BRIDJ — 세리프 금, 자간 넓게. 우측 영역에 맞춰 자동 축소.
    word = "GOGA BRIDJ"
    wx = 575
    avail = W - wx - 48                       # 우측 여백
    size, tracking = 96, 6
    while size > 40:
        wm = _font(size)
        tracking = max(2, size // 16)
        width = sum(d.textlength(ch, font=wm) + tracking for ch in word) - tracking
        if width <= avail:
            break
        size -= 4
    wm = _font(size)
    bbox = wm.getbbox("G")
    wy = (H - (bbox[3] - bbox[1])) // 2 - 36
    end_x = _text_spaced(d, (wx, wy), word, wm, GOLD, tracking=tracking)

    # 금 헤어라인 + 라틴 서브(한글 폰트 의존 회피)
    rule_y = wy + size + 24
    d.line([(wx + 2, rule_y), (min(end_x - 4, W - 48), rule_y)], fill=(201, 162, 75, 140), width=2)
    sub = _font(32)
    d.text((wx + 2, rule_y + 18), "Global commerce bridge", font=sub, fill=CREAM)

    card.convert("RGB").save(OUT_STATIC)
    card.convert("RGB").save(OUT_VENDOR)
    print(f"OG 카드 생성: {OUT_STATIC} + {OUT_VENDOR} ({W}x{H})")


if __name__ == "__main__":
    main()
