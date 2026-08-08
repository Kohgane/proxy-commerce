"""v86-H 판정 캡처 — 목록 페이지 extracted 오염 before/after.

before = 억제 게이트 없음(= 1.5.138 동작). after = 이번 수리.
수치는 **실제 실행 결과**만 싣는다 — tests/test_v86_h_list_purity.py와 **같은 하네스**(jsdom +
라이브 kgp-extractor.js)를 오너 커밋 스냅샷에 물려 돌린 값을 그대로 그린다. 손으로 적은 숫자 0.

이 판정에는 화면(UI) 변경이 없다. 값의 대조가 산출물이므로 브라우저 렌더가 아니라 PIL로 그린다.
"""
from __future__ import annotations

import re

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

OUT = ROOT / "docs" / "screens" / "v86" / "h-list-purity.png"

INK, PAPER, GOLD, TEAL, ORANGE, MUTED = (
    (26, 23, 20), (245, 239, 227), (201, 162, 75), (17, 154, 142), (245, 130, 31), (138, 127, 112),
)


def _measure():
    import test_v86_h_list_purity as H   # noqa: E402

    broken = H.EXTRACTOR.replace('if (_pageType === "list") {', 'if (_pageType === "__never__") {', 1)
    rak_before = H._extract(H.SNAP_RAKUTEN, H.URL_RAKUTEN, opts='{pageType:"list"}', src=broken)
    rak_after = H._extract(H.SNAP_RAKUTEN, H.URL_RAKUTEN, opts='{pageType:"list"}')
    ali_before = H._extract(H.SNAP_ALI, H.URL_ALI, opts='{pageType:"list"}', src=broken)
    ali_after = H._extract(H.SNAP_ALI, H.URL_ALI, opts='{pageType:"list"}')
    return rak_before, rak_after, ali_before, ali_after


def _icons(imgs):
    return [u for u in imgs if any(t in u for t in ("/48x48.", "/60x60.", "/45x60.", "/154x64.", "/190x64.", "/702x72."))]


def _rows(rak, ali):
    junk = [v for v in rak["optValues"] if v in ("北海道", "青森県", "東京都", "沖縄県")]
    return [
        ("라쿠텐 · 제목", (rak["title"] or "(비어 있음)")[:30], not rak["title"]),
        ("라쿠텐 · 가격", (rak["price"] or "(비어 있음)"), not rak["price"]),
        ("라쿠텐 · 옵션 값 수", str(len(rak["optValues"])) + ("  ← 도도부현·정렬·리뷰필터" if rak["optValues"] else ""), not rak["optValues"]),
        ("라쿠텐 · 도도부현 유입", (", ".join(junk[:3]) or "없음"), not junk),
        ("라쿠텐 · 상세설명", (rak["desc"] or "(비어 있음)")[:30], not rak["desc"]),
        ("알리 · 이미지 장수", str(len(ali["images"])), True),
        ("알리 · 아이콘/배너 혼입", str(len(_icons(ali["images"]))) + "장", not _icons(ali["images"])),
        ("억제 사유 기록", str((rak["suppressed"] or {}).get("fields", "없음"))[:34], bool(rak["suppressed"])),
    ]


def _font(size: int, bold: bool = False, jp: bool = False):
    """한글은 맑은고딕, 일본어(가나·한자)는 메이리오 — 한 폰트로는 한·일 실측값이 모두 안 나온다.

    맑은고딕은 상용한자 일부가 비어 두부(□)가 되고, 메이리오/MS고딕은 한글이 없다.
    그래서 **문자열 내용으로 폰트를 고른다**(값이 그대로 읽히는 게 판정 캡처의 전부).
    """
    from PIL import ImageFont

    if jp:
        names = ("meiryob.ttc", "meiryo.ttc", "msgothic.ttc") if bold else ("meiryo.ttc", "msgothic.ttc")
    else:
        names = ("malgunbd.ttf", "malgun.ttf") if bold else ("malgun.ttf",)
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


_JP_RE = re.compile(r"[぀-ヿ㐀-鿿]")


def _font_for(text: str, size: int, bold: bool = False):
    return _font(size, bold, jp=bool(_JP_RE.search(str(text))))


def main() -> int:
    from PIL import Image, ImageDraw

    rb, ra, ab, aa = _measure()
    W, H = 1120, 620
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    f_h, f_t, f_b, f_s = _font(23, True), _font(15), _font(15, True), _font(13)

    d.text((28, 22), "v86-H 판정 — 목록 페이지가 상품 필드를 오염시키는가", font=f_h, fill=INK)
    d.line((28, 58, W - 28, 58), fill=GOLD, width=2)
    d.text((28, 68), "오너 커밋 진단 스냅샷(라쿠텐 검색·알리 목록) + 라이브 kgp-extractor.js 실행 결과 — 테스트와 동일 하네스",
           font=f_s, fill=MUTED)

    for i, (title, rak, ali, tint) in enumerate(
        [("BEFORE — 억제 게이트 없음(1.5.138)", rb, ab, ORANGE),
         ("AFTER — 목록 갈래 억제 + 이미지 크기 게이트", ra, aa, TEAL)]
    ):
        x = 28 + i * (W // 2 - 8)
        w = W // 2 - 36
        d.rectangle((x, 102, x + w, H - 28), fill=(255, 255, 255), outline=(226, 218, 204))
        d.rectangle((x, 102, x + 4, H - 28), fill=tint)
        d.text((x + 18, 116), title, font=f_b, fill=INK)
        y = 152
        for label, value, ok in _rows(rak, ali):
            d.text((x + 18, y), label, font=f_s, fill=MUTED)
            d.text((x + 18, y + 18), str(value)[:44], font=_font_for(value, 15), fill=(INK if ok else ORANGE))
            y += 52

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
