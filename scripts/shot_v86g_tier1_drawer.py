"""v86-G 판정 캡처 — 편집 드로어의 Tier1 판정 줄(채택 URL 표기) before/after.

before = 종전 템플릿(`_t1.source` 조회) — 확장이 키를 `tier1_source`로 바꾼 뒤부터 **항상**
         'API 응답'으로만 보였다(어떤 응답을 채택했는지 화면에서 사라진 조용한 회귀).
after  = 이번 수정 — 실제 채택 URL 표기 + 추천 블록 배제(스코프) 표기.

실제 템플릿(collect_preview.html)을 그대로 렌더한다. before는 그 한 줄만 종전 표현식으로
되돌린 상태에서 찍고 즉시 복원한다 — 목업 HTML을 따로 짜면 추측 캡처가 되므로 금지.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = ROOT / "src" / "seller_console" / "templates" / "collect_preview.html"
OUT = ROOT / "docs" / "screens" / "v86" / "g-tier1-drawer.png"
PORT = 5186

NEW_EXPR = "{{ (_t1.tier1_source or _t1.source or 'API 응답')[:64] }}"
OLD_EXPR = "{{ (_t1.source or 'API 응답')[:64] }}"
NEW_SCOPE = "{% if _t1.tier1_scope and _t1.tier1_scope.scoped %} · <span class=\"text-muted\">추천 상품 블록 배제</span>{% endif %}"

# 확장 1.5.138이 실제로 싣는 모양(_kgpTier1Diag) 그대로.
TIER1_DIAG = {
    "used": True,
    "netBound": True,
    "tier1_source": "https://www.temu.com/api/oak/integration/render?scene=goods_detail",
    "tier1_hits": 1, "tier1_seen": 14, "tier1_jsonish": 9, "tier1_dropped": 8,
    "topScore": 3, "cause": "",
    "page_goods_id": "601099512345678", "goods_matched": True,
    "goods_ids_n": 21,
    "tier1_scope": {"scoped": True, "reason": "narrowed"},
}


def _seed() -> str:
    from src.seller_console import collect_history_store as ch
    import src.seller_console.views as views

    views._seller_identities = lambda: {"u1"}
    views._seller_id = lambda: "u1"
    ch._in_memory.clear()
    extra = {
        "title": "폴더블 차량용 테이블",
        "price": "12900", "currency": "KRW",
        "images": ["https://img.kwcdn.com/product/m1.jpg"],
        "options": [{"name": "색상", "values": "블랙, 화이트"}],
        "tier1_diag": TIER1_DIAG,
    }
    return ch.append(source="extension", url="https://www.temu.com/kr/x-g-601099512345678.html",
                     title=extra["title"], image=extra["images"][0], price="12900",
                     currency="KRW", extra=extra, seller_id="u1")


def _shoot(page, iid: str, path: Path) -> None:
    from src.order_webhook import app

    app.jinja_env.cache.clear()          # 디스크의 현재 템플릿으로 다시 컴파일
    page.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1",
              wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    det = page.locator("details:has-text('수집 로그 보기')").first
    det.evaluate("d => d.open = true")
    page.wait_for_timeout(200)
    det.screenshot(path=str(path))


def main() -> int:
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app

    iid = _seed()
    # Jinja는 템플릿을 캐시한다 — 끄지 않으면 before 렌더가 캐시돼 after가 **같은 화면**으로 찍힌다
    #   (거짓 캡처). 파일을 바꿔 가며 찍는 이 스크립트에선 반드시 자동 리로드 + 캐시 비우기.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
    time.sleep(2)

    src = TPL.read_text(encoding="utf-8")
    assert NEW_EXPR in src and NEW_SCOPE in src, "수정된 표현식을 못 찾았다 — 캡처가 거짓이 된다"
    tmp = ROOT / "docs" / "screens" / "v86"
    tmp.mkdir(parents=True, exist_ok=True)
    before_png, after_png = tmp / "_g-t1-before.png", tmp / "_g-t1-after.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 900, "height": 600}).new_page()
        try:
            TPL.write_text(src.replace(NEW_EXPR, OLD_EXPR).replace(NEW_SCOPE, ""), encoding="utf-8")
            _shoot(page, iid, before_png)
        finally:
            TPL.write_text(src, encoding="utf-8")      # 원본 복원(실패해도 반드시)
        _shoot(page, iid, after_png)
        browser.close()

    from PIL import Image, ImageDraw, ImageFont

    def _f(sz, bold=False):
        for n in (("malgunbd.ttf", "malgun.ttf") if bold else ("malgun.ttf",)):
            try:
                return ImageFont.truetype(n, sz)
            except OSError:
                continue
        return ImageFont.load_default()

    b, a = Image.open(before_png), Image.open(after_png)
    W = max(b.width, a.width) + 48
    H = b.height + a.height + 150
    img = Image.new("RGB", (W, H), (245, 239, 227))
    d = ImageDraw.Draw(img)
    d.text((24, 20), "BEFORE — 채택 URL이 항상 'API 응답'(키 이름 변경 미반영)", font=_f(15, True), fill=(26, 23, 20))
    img.paste(b, (24, 48))
    y = 48 + b.height + 30
    d.text((24, y), "AFTER — 실제 채택 URL + 추천 블록 배제 표기", font=_f(15, True), fill=(26, 23, 20))
    img.paste(a, (24, y + 28))
    img.save(OUT)
    before_png.unlink(missing_ok=True)
    after_png.unlink(missing_ok=True)
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
