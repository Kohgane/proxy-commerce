"""M3-iOS 보충 캡처 — 폰 폭 390px.

after: 화면 A(설치하기)·B(사용하기)·C(오너) · 결과 화면(타오바오 공유 = 담았어요 · 테무 링크 = 담지 못했어요).
before(main): 테무 링크 공유 → 빈 상품이 「담았어요」로 저장(가짜 성공).
사용: python scripts/_devshot_m3ios.py <before|after> <out_dir>
"""
import os
import sys
import threading
from urllib.parse import quote

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
SHARE = ("【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356\n"
         "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n"
         "点击链接直接打开 或者 淘宝搜索直接打开")
TEMU = "https://www.temu.com/kr/goods.html?goods_id=601099512345"


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.collectors import link_diag
    link_diag.resolve_short_link = lambda url: {"ok": False, "reason": "offline"}
    from src.order_webhook import app
    import scripts._devshot_f51 as base

    @app.before_request
    def _as_admin():                        # 캡처용: 화면 C는 관리자만
        from flask import session
        session["user_id"], session["user_role"] = "owner", "admin"

    srv = make_server("127.0.0.1", 5196, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    pages = [("temu", "/seller/collect/share?text=" + quote(TEMU))]
    if TAG == "after":
        pages = [("install", "/seller/guide/iphone"), ("use", "/seller/guide/iphone/use"),
                 ("make", "/seller/guide/iphone/make"),
                 ("done", "/seller/collect/share?text=" + quote(SHARE))] + pages
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for key, path in pages:
                pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5196") else r.abort())
                resp = pg.goto("http://127.0.0.1:5196" + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(900)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(300)
                pg.screenshot(path=f"{OUT}/m3ios-{key}-{TAG}.png", full_page=key in ("install", "use", "make"))
                state = pg.evaluate("() => { const e = document.querySelector('[data-role=share-state]'); return e ? e.innerText : ''; }")
                print(f"[{TAG}/{key}] HTTP {resp.status if resp else '?'} 상태='{state}'")
                pg.close()
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
