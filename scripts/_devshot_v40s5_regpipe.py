"""개발용 스크린샷 — 디자인 v2 Stage 5: register-pipe 전면 재설계 before/after.

같은 검수 데이터로 origin/main 템플릿(BEFORE) ↔ 작업본(AFTER)을 풀페이지 렌더한다.
라우트를 태우지 않고 `render_template`로 직접 그린다(수집·네트워크 의존 0).
"""
import io
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/register_pipe.html"
CSS = "src/static/app.css"
SELLER_CSS = "src/seller_console/static/seller.css"
CONSOLE_CSS = "src/seller_console/static/console.css"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s5"


def _row(**kw):
    base = {
        "url": "https://www.amazon.de/dp/B0GS4698H2", "title_ko": "Fellow Stagg EKG 전기주전자 무광 블랙",
        "thumbnail": "", "cost_krw": 620000, "sale_krw": 894000, "margin_pct": 30.6,
        "net_krw": 273900, "target_margin_pct": 38.0, "ship_status": "배송가능",
        "ship_reason": "독일 → 한국 직배송 확인", "ship_over_35pct": False,
        "excluded": False, "warnings": [], "title_truncated": False,
        "title_truncated_suspect": False, "title_cjk_residual": False,
        "cost_basis": "", "price_reason": "", "forbidden_detail": None,
        "notice_preview": {"제조자": "Fellow", "수입자": "고가네", "원산지": "중국",
                           "origin_source": "meta", "origin_source_ko": "상세페이지 실측",
                           "origin_verified": True, "origin_inferred": False},
    }
    base.update(kw)
    return base


REVIEW = {
    "requested": 6, "blacklist_count": 3412, "fx_usd_krw": 1385.0, "capped": False,
    "review_pass": [
        _row(),
        _row(url="https://item.rakuten.co.jp/yoshidakaban/1234", title_ko="포터 탱커 숄더백 2WAY 블랙",
             cost_krw=284000, sale_krw=419000, margin_pct=27.4, net_krw=114800,
             notice_preview={"제조자": "요시다카반", "수입자": "고가네", "원산지": "일본",
                             "origin_source": "brand", "origin_source_ko": "브랜드 본사국",
                             "origin_verified": False, "origin_inferred": True}),
        _row(url="https://www.ystudiostyle.com/products/classic", title_ko="와이스튜디오 클래식 만년필 브라스",
             cost_krw=176000, sale_krw=268000, margin_pct=24.9, net_krw=66700,
             ship_status="미검증", ship_reason="실측 전", title_cjk_residual=True),
        _row(url="https://www.amazon.co.jp/dp/B09XYZ", title_ko="울란지 삼각대 미니 카본",
             cost_krw=98000, sale_krw=0, margin_pct=None, net_krw=None,
             price_reason="환율 미상 — 환산 불가", ship_status="미검증", ship_reason="실측 전",
             warnings=[{"label": "배송비 미상", "reason": "배송비를 못 구해 마진 미반영"}]),
    ],
    "excluded": [
        _row(url="https://www.amazon.com/dp/B0FAKE01", title_ko="에어팟 프로 2 호환 실리콘 케이스",
             excluded=True, cost_krw=32000, sale_krw=0, margin_pct=None, net_krw=None,
             forbidden_detail={"kind_ko": "금지 브랜드", "term": "에어팟", "snippet": "…에어팟 프로 2…"},
             notice_preview=None),
    ],
    "failed": [{"url": "https://www.temu.com/g-601150655669129.html", "reason": "봇 차단(403)"}],
}


def _render(html_path, app_css: str):
    """렌더 후 **CSS를 인라인으로 박아** 저장한다 — CDN(부트스트랩·폰트)은 프록시가 막는다."""
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/sourcing/register-pipe"):
        html = render_template("register_pipe.html", page="sourcing", review=REVIEW, urls_text="")
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + app_css + "</style>"
    for extra in (SELLER_CSS, CONSOLE_CSS):        # 콘솔 chrome(사이드바 등)도 실제대로
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    html = html.replace("</head>", inline + "</head>", 1) if "</head>" in html else inline + html
    open(html_path, "w", encoding="utf-8").write(html)


def main():
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    files = {f: subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True,
                               text=True).stdout for f in (TPL, CSS)}
    cur = {f: open(f, encoding="utf-8").read() for f in (TPL, CSS)}
    shots = {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for tag, src in (("BEFORE", files), ("AFTER", cur)):
                for f, content in src.items():
                    open(f, "w", encoding="utf-8").write(content)
                out_html = f"/tmp/_s5_{tag}.html"
                _render(out_html, src[CSS])
                pg = br.new_page(viewport={"width": 1280, "height": 900},
                                 device_scale_factor=2)
                pg.goto(f"file://{out_html}")
                pg.wait_for_timeout(900)
                main = pg.query_selector("main") or pg.query_selector(".console-content")
                shots[tag] = (main.screenshot() if main else pg.screenshot(full_page=True))
                pg.close()
            br.close()
    finally:
        for f, content in cur.items():
            open(f, "w", encoding="utf-8").write(content)

    os.makedirs(OUT_DIR, exist_ok=True)
    for tag in ("BEFORE", "AFTER"):
        open(f"{OUT_DIR}/regpipe-{tag.lower()}.png", "wb").write(shots[tag])
    ims = {t: Image.open(io.BytesIO(shots[t])) for t in shots}
    h = max(i.height for i in ims.values()) + 44
    w = sum(i.width for i in ims.values())
    canvas = Image.new("RGB", (w, h), (251, 248, 241))
    d = ImageDraw.Draw(canvas)
    x = 0
    for tag in ("BEFORE", "AFTER"):
        d.text((x + 16, 12), f"{tag}", fill=(26, 23, 20))
        canvas.paste(ims[tag], (x, 40))
        x += ims[tag].width
    canvas.save(f"{OUT_DIR}/regpipe-before-after.png")
    print("saved", OUT_DIR, {t: ims[t].size for t in ims})


if __name__ == "__main__":
    main()
