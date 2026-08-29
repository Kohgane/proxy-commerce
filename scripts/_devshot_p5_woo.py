"""개발용 스크린샷 — P5 WooCommerce 어댑터 편입(등록 파이프 마켓 select).

BEFORE(쿠팡·스마트스토어 2택) vs AFTER(멀티샵 추가 + 단일 계정 + '심사 없음·draft' 안내).
템플릿을 origin/main↔작업본으로 스왑해 **같은 검수표 데이터**로 두 번 렌더한다.
라우트를 태우지 않고 `render_template`로 직접 그린다(수집·네트워크 의존 0).
"""
import io
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/register_pipe.html"
OUT = "docs/screens/regpipe/p5-woocommerce-market-select.png"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

REVIEW = {
    "requested": 1,
    "review_pass": [{"url": "https://www.amazon.de/dp/B0GS4698H2", "title_ko": "Fellow Stagg 전기주전자 EKG",
                     "sale_krw": 894000, "asin": "B0GS4698H2", "source": "amazon.de",
                     "cost_krw": 620000, "margin_pct": 30.6, "image_count": 7,
                     "category_code": "HOM", "title_en": "Fellow Stagg EKG Electric Kettle",
                     "net_krw": 273900, "fee_krw": 89400, "ship_krw": 12000,
                     "cost_usd": 429.0, "currency": "EUR", "price_original": 399.0,
                     "flags": [], "notes": ""}],
    "excluded": [], "failed": [],
}


def _render(html_path):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()                          # 스왑한 템플릿을 다시 읽게 한다
    with app.test_request_context("/seller/sourcing/register-pipe"):
        html = render_template("register_pipe.html", page="sourcing", review=REVIEW, urls_text="")
    open(html_path, "w", encoding="utf-8").write(html)


def main():
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    base = subprocess.run(["git", "show", f"origin/main:{TPL}"], capture_output=True, text=True).stdout
    cur = open(TPL, encoding="utf-8").read()
    shots = {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for tag, content in (("BEFORE", base), ("AFTER", cur)):
                open(TPL, "w", encoding="utf-8").write(content)
                out_html = f"/tmp/_p5_{tag}.html"
                _render(out_html)                       # Jinja 캐시는 _render가 비운다
                pg = br.new_page(viewport={"width": 1120, "height": 640})
                pg.goto(f"file://{out_html}")
                # 부트스트랩 CDN은 에이전트 프록시가 차단 → 로컬 사본 주입(앱 무변경·v34 선례).
                if os.path.exists(BOOTSTRAP):
                    pg.add_style_tag(path=BOOTSTRAP)
                pg.wait_for_timeout(600)
                if tag == "AFTER":
                    pg.select_option("#p3Market", "woocommerce")
                    pg.wait_for_timeout(300)
                el = pg.query_selector("#p3Market")
                el.scroll_into_view_if_needed() if el else None
                pg.wait_for_timeout(200)
                card = pg.query_selector("#p3Market >> xpath=ancestor::div[contains(@class,'card')][1]")
                shots[tag] = (card or pg).screenshot()
                pg.close()
            br.close()
    finally:
        open(TPL, "w", encoding="utf-8").write(cur)

    ims = [Image.open(io.BytesIO(shots[t])) for t in ("BEFORE", "AFTER")]
    w = max(i.width for i in ims)
    h = sum(i.height for i in ims) + 72
    canvas = Image.new("RGB", (w, h), (251, 248, 241))
    d = ImageDraw.Draw(canvas)
    y = 0
    # PIL 기본 폰트는 한글을 못 그린다 — 캡션은 ASCII로(화면 본문은 브라우저가 렌더).
    for tag, im in zip(("BEFORE - markets: Coupang / SmartStore",
                        "AFTER  - + Multishop (single account, no review, draft)"), ims):
        d.text((14, y + 10), tag, fill=(26, 23, 20))
        canvas.paste(im, (0, y + 34))
        y += im.height + 36
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    canvas.save(OUT)
    print("saved", OUT, canvas.size)


if __name__ == "__main__":
    main()
