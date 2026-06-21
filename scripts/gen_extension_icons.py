"""scripts/gen_extension_icons.py — 코고가네 크롬 확장 액션 아이콘 생성 (v8 ③).

브랜드 팔레트(먹 #1a1714 / 금 #c9a24b / 청록 #119a8e)로 글러브(🧤) 모노그램을
그려 16/32/48/128 PNG를 만든다. 북마클릿 🧤·디자인 토큰과 통일.

고해상도(4x)로 렌더 후 LANCZOS 다운샘플 → 작은 크기에서도 또렷.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

INK = (26, 23, 20, 255)        # 먹
INK_HI = (40, 35, 30, 255)     # 먹 하이라이트
GOLD = (201, 162, 75, 255)     # 금
GOLD_HI = (224, 188, 110, 255)  # 금 하이라이트
TEAL = (17, 154, 142, 255)     # 청록

OUT = Path("extensions/chrome-collector/icons")
SIZES = [16, 32, 48, 128]
SS = 8  # supersample factor


def _rrect(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(px: int) -> Image.Image:
    """단위 정사각형 기준으로 글러브 모노그램을 그린다."""
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def u(v: float) -> float:
        return v * S

    # 둥근 사각 먹 배경 + 금 테두리
    pad = u(0.02)
    _rrect(d, [pad, pad, S - pad, S - pad], radius=u(0.22), fill=INK)
    # 살짝 위쪽 하이라이트(입체)
    _rrect(d, [pad, pad, S - pad, u(0.5)], radius=u(0.22), fill=INK_HI)
    _rrect(d, [pad, u(0.28), S - pad, S - pad], radius=u(0.16), fill=INK)

    # 청록 궤도(브랜드 악센트) — 우상단에서 좌하단으로 가는 얇은 호
    d.arc([u(0.12), u(0.10), u(0.92), u(0.90)], start=-35, end=120,
          fill=TEAL, width=max(2, int(u(0.035))))

    # 글러브(미튼) — 금. 손등(둥근 사각) + 엄지(타원) + 청록 소맷동.
    # 손등
    _rrect(d, [u(0.34), u(0.20), u(0.74), u(0.66)], radius=u(0.16), fill=GOLD)
    # 손등 하이라이트
    _rrect(d, [u(0.37), u(0.22), u(0.71), u(0.40)], radius=u(0.14), fill=GOLD_HI)
    # 엄지(왼쪽 타원)
    d.ellipse([u(0.22), u(0.34), u(0.42), u(0.58)], fill=GOLD)
    # 소맷동(청록 밴드) — 글러브 아래
    _rrect(d, [u(0.32), u(0.62), u(0.76), u(0.78)], radius=u(0.06), fill=TEAL)

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        render(s).save(OUT / f"{s}.png")
        print(f"wrote {OUT}/{s}.png")


if __name__ == "__main__":
    main()
