"""scripts/gen_favicon_glove.py — 코고가네 글러브 파비콘/앱 아이콘 생성 (v13).

브랜드 마크(글러브 모노그램, 먹/금/청록)로 favicon.ico·apple-touch-icon·icon-192·icon-512를
생성한다. 지구본 폐기. 4x 슈퍼샘플 후 LANCZOS 다운샘플.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

INK = (26, 23, 20, 255)        # 먹
GOLD = (201, 162, 75, 255)     # 금
GOLD_HI = (224, 188, 110, 255)  # 금 하이라이트
TEAL = (17, 154, 142, 255)     # 청록

OUT = Path("src/seller_console/static")
SS = 4  # supersample


def _rrect(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def render(px: int, *, rounded: bool = True) -> Image.Image:
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def u(v: float) -> float:
        return v * S

    # 먹 배경(둥근 사각)
    _rrect(d, [0, 0, S, S], r=(u(0.22) if rounded else 0), fill=INK)
    # 청록 궤도 호
    d.arc([u(0.10), u(0.12), u(0.92), u(0.94)], start=-35, end=120, fill=TEAL, width=max(2, int(u(0.045))))
    # 엄지
    d.ellipse([u(0.22), u(0.34), u(0.42), u(0.60)], fill=GOLD)
    # 손등 + 하이라이트
    _rrect(d, [u(0.36), u(0.20), u(0.74), u(0.66)], r=u(0.16), fill=GOLD)
    _rrect(d, [u(0.385), u(0.225), u(0.715), u(0.42)], r=u(0.14), fill=GOLD_HI)
    # 청록 소맷동
    _rrect(d, [u(0.34), u(0.62), u(0.76), u(0.78)], r=u(0.06), fill=TEAL)

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(180).save(OUT / "apple-touch-icon.png")
    render(192).save(OUT / "icon-192.png")
    render(512).save(OUT / "icon-512.png")
    # favicon.ico — 다중 크기 내장
    ico = render(64)
    ico.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    for n in ("apple-touch-icon.png", "icon-192.png", "icon-512.png", "favicon.ico"):
        print("wrote", OUT / n)


if __name__ == "__main__":
    main()
