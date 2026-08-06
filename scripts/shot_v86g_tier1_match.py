"""v86-G 판정 캡처 — 테무 Tier1: 추천 동봉 응답에서 수집이 살아나는가(before/after).

before = 종전 매칭(응답당 대표 goods_id 1개 == 내 id) — 추천 상품 id가 대표로 잡히면 Tier1 **전량 폐기**
after  = 이번 수리(응답 안 goods_id 집합으로 매칭 + 내 goods 서브트리로 스코프 축소)

★수치는 **실제 실행 결과**만 싣는다. 이 스크립트는 tests/test_v86_g_tier1_match.py와 **같은 하네스**
  (jsdom + 라이브 kgp-net.js/kgp-extractor.js)를 돌려 나온 JSON을 그대로 그린다 — 손으로 적은 숫자 0.
  브라우저 렌더가 아니라 PIL로 그리는 이유: 이 판정에는 화면(UI) 변경이 없고 값의 대조가 산출물이다.

사용: python scripts/shot_v86g_tier1_match.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "screens" / "v86" / "g-tier1-match.png"

# 색: 고가브릿지 토큰(먹/한지/금/청록/주황)
INK, PAPER, GOLD, TEAL, ORANGE, MUTED = (
    (26, 23, 20), (245, 239, 227), (201, 162, 75), (17, 154, 142), (245, 130, 31), (138, 127, 112),
)


def _measure() -> tuple[dict, dict]:
    """테스트와 동일한 하네스를 그대로 재사용한다(별도 구현 금지 — 두 숫자가 갈리면 캡처가 거짓이 된다)."""
    sys.path.insert(0, str(ROOT / "tests"))
    import test_v86_g_tier1_match as H   # noqa: E402

    before = H._run(singleIdMatch=True)   # 종전 방식
    after = H._run()                      # 수리 후
    return before, after


def _rows(got: dict) -> list[tuple[str, str, bool]]:
    ok_price = got["price"] == "12900"
    ok_opt = bool(got["options"]) and "추천색" not in " ".join(got["options"])
    ok_gal = len(got["gallery"]) == 3
    cap = got.get("capture") or {}
    return [
        ("응답 안 goods_id 수", str(len(cap.get("goods_ids") or [])) + " (내 상품 + 추천)", True),
        ("대표 goods_id", cap.get("goods_id") or "-", True),
        ("내 상품 매칭", "성공" if got["matched"] else "실패 → Tier1 전량 폐기", got["matched"]),
        ("스코프", (got.get("scope") or {}).get("reason") or "-", bool(got.get("scope"))),
        ("가격", got["price"] or "(공백)", ok_price),
        ("옵션", ", ".join(got["options"]) or "(공백)", ok_opt),
        ("갤러리", f"{len(got['gallery'])}장", ok_gal),
        ("가격 출처", got["field_sources"].get("price") or "none", got["field_sources"].get("price") == "tier1"),
    ]


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    for name in (("malgunbd.ttf", "malgun.ttf") if bold else ("malgun.ttf",)):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> int:
    from PIL import Image, ImageDraw

    before, after = _measure()
    W, H = 1040, 620
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    f_h, f_t, f_b, f_s = _font(24, True), _font(15), _font(15, True), _font(13)

    d.text((28, 24), "v86-G 판정 — 테무 Tier1: 추천 동봉 응답에서 수집이 살아나는가", font=f_h, fill=INK)
    d.line((28, 60, W - 28, 60), fill=GOLD, width=2)
    d.text((28, 70), "jsdom + 라이브 kgp-net.js/kgp-extractor.js 실행 결과(테스트와 동일 하네스)",
           font=f_s, fill=MUTED)

    for i, (title, got, tint) in enumerate(
        [("BEFORE — 대표 id 1개 매칭(종전)", before, ORANGE),
         ("AFTER — id 집합 매칭 + goods 서브트리 스코프", after, TEAL)]
    ):
        x = 28 + i * (W // 2 - 8)
        w = W // 2 - 36
        d.rectangle((x, 104, x + w, H - 28), fill=(255, 255, 255), outline=(226, 218, 204))
        d.rectangle((x, 104, x + 4, H - 28), fill=tint)
        d.text((x + 18, 118), title, font=f_b, fill=INK)
        y = 156
        for label, value, ok in _rows(got):
            d.text((x + 18, y), label, font=f_s, fill=MUTED)
            d.text((x + 18, y + 18), str(value)[:46], font=f_t, fill=(INK if ok else ORANGE))
            y += 52

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
