#!/usr/bin/env python3
"""v21: 게이트웨이(B) 브랜드 마크 raster 생성 — favicon/PWA/확장/스토어.

cairosvg 없이 Pillow로 favicon.svg와 동일한 기하(먹 vault + 금 게이트웨이 아치 +
주황 키스톤)를 그려 모든 사이즈 PNG/ICO를 만든다. 4x 슈퍼샘플로 가장자리 매끈하게.
글러브/지구본 폐기.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SELLER_STATIC = ROOT / "src" / "seller_console" / "static"
EXT_ICONS = ROOT / "extensions" / "chrome-collector" / "icons"

INK = (26, 23, 20, 255)        # #1A1714 먹
GOLD = (201, 162, 75, 255)     # #C9A24B 금
ORANGE = (245, 130, 31, 255)   # #F5821F 주황
GOLD_FAINT = (201, 162, 75, 90)  # 키라인(35% 불투명 ≈ 90/255)

SS = 4  # supersample


def _draw_mark(size: int) -> Image.Image:
    """게이트웨이 마크 한 장(RGBA, opaque vault)."""
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def s(v: float) -> float:  # 정규화(0..1) → 픽셀
        return v * S

    # 먹 vault(라운드 사각 배경)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=s(0.22), fill=INK)
    # 금 키라인 보더
    d.rounded_rectangle(
        [s(0.047), s(0.047), S - s(0.047), S - s(0.047)],
        radius=s(0.18), outline=GOLD_FAINT, width=max(1, int(s(0.012))),
    )

    cx, cy = s(0.5), s(0.46)
    r_out, r_in = s(0.28), s(0.165)
    y_base = s(0.80)

    # 금 게이트웨이 몸체 = 사각 기둥(중심선 아래) + 반원(위)
    d.rectangle([cx - r_out, cy, cx + r_out, y_base], fill=GOLD)
    d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=GOLD)
    # 먹 통로 = 안쪽을 같은 방식으로 파냄 → 균일 아치 밴드
    d.rectangle([cx - r_in, cy, cx + r_in, y_base], fill=INK)
    d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=INK)

    # 금 지반/다리 상판
    d.rounded_rectangle([s(0.16), y_base, s(0.84), s(0.875)], radius=s(0.024), fill=GOLD)

    # 주황 키스톤(아치 정점 쐐기)
    d.polygon(
        [(s(0.44), s(0.155)), (s(0.56), s(0.155)), (s(0.54), s(0.335)), (s(0.46), s(0.335))],
        fill=ORANGE,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    # 사이트(셀러 정적): favicon.ico(16/32/48) + apple-touch(180) + 192/512 + 스토어 1024
    base = _draw_mark(1024)
    base.save(SELLER_STATIC / "icon-1024.png")                 # App Store
    _draw_mark(512).save(SELLER_STATIC / "icon-512.png")       # Play / PWA maskable
    _draw_mark(192).save(SELLER_STATIC / "icon-192.png")       # PWA
    _draw_mark(180).save(SELLER_STATIC / "apple-touch-icon.png")
    ico48 = _draw_mark(48)
    ico48.save(SELLER_STATIC / "favicon.ico", format="ICO",
               sizes=[(16, 16), (32, 32), (48, 48)])

    # 크롬 확장 툴바
    for px in (16, 32, 48, 128):
        _draw_mark(px).save(EXT_ICONS / f"{px}.png")

    print("게이트웨이 아이콘 생성 완료: favicon.ico, apple-touch-icon.png, "
          "icon-192/512/1024.png, 확장 16/32/48/128.png")


if __name__ == "__main__":
    main()
