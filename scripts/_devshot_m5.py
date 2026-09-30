"""M5 캡처 — 폰 폭 390px: 공유로 담기 → 결과 화면 카드 → 사전검증 → 등록 완료. 매 단계 가로 스크롤 측정.

마켓 호출은 캡처용 가짜 디스패처(쿠팡 통과·스마트스토어 자격 없음 → 쿠팡만 등록, 상품 ID 16400000001).
before(main): 결과 화면에 제목만 — 등록하려면 데스크톱 편집 화면으로 가야 했다.
사용: python scripts/_devshot_m5.py <before|after> <out_dir>
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
         "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n点击链接直接打开 或者 淘宝搜索直接打开")


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.collectors import link_diag
    link_diag.resolve_short_link = lambda url: {"ok": False, "reason": "offline"}
    import src.seller_console.views as V
    from src.order_webhook import app
    import scripts._devshot_f51 as base

    try:
        from src.seller_console.upload_dispatcher import DispatchResult, UploadResult

        class _Disp:
            def prevalidate(self, product, markets):
                return [type("R", (), {"market": m, "ok": m == "coupang", "error_code": "",
                                       "message": "" if m == "coupang" else "스마트스토어 연동 정보가 없어요",
                                       "hint": "", "reach_ok": None, "reach_ms": None, "reach_detail": "",
                                       "details": [], "action_url": "" if m == "coupang" else "/seller/markets/connect/smartstore"})()
                        for m in markets]

            def dispatch(self, product, markets):
                return DispatchResult(product_url="", total=1, succeeded=1, results=[
                    UploadResult(market="coupang", success=True, message="쿠팡 업로드 성공",
                                 external_product_id="16400000001")])
        V._get_upload_dispatcher = lambda: _Disp()
        import src.services.image_reachability as ir
        ir.check_all = lambda urls, labels=None: {"ok": True, "bad": []}
    except Exception as exc:
        print("dispatcher stub skipped:", exc)

    @app.before_request
    def _as_user():
        from flask import session
        session["user_id"] = "u-m5-shot"

    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://detail.1688.com/offer/7788.html", title="원목 책상 120cm",
                   price="199", currency="CNY", seller_id="u-m5-shot",
                   extra={"title": "원목 책상 120cm", "title_ko": "원목 책상 120cm", "price": "199", "currency": "CNY",
                          "images": ["/seller/static/icon-512.png"],
                          "skus": [{"spec": ["원목", "120cm"], "price": "199", "currency": "CNY"},
                                   {"spec": ["원목", "140cm"], "price": "239", "currency": "CNY"},
                                   {"spec": ["호두나무", "140cm"], "price": "259", "currency": "CNY"}]})

    srv = make_server("127.0.0.1", 5200, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    B = "http://127.0.0.1:5200"
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
            pg = ctx.new_page()

            def shot(key, full=True):
                pg.wait_for_timeout(600)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(250)
                pg.screenshot(path=f"{OUT}/m5-{key}-{TAG}.png", full_page=full)
                sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                state = pg.evaluate("() => { const e = document.querySelector('[data-role=share-state]'); return e ? e.innerText : ''; }")
                print(f"[{TAG}/{key}] scrollWidth={sw[0]} clientWidth={sw[1]} hscroll={'있음' if sw[0] > sw[1] else '없음'} 상태='{state}'")

            pg.goto(B + "/seller/collect/share?src=share&text=" + quote(SHARE))
            shot("share")
            if TAG == "after":
                pg.goto(B + f"/seller/m/item/{iid}")
                shot("card")
                pg.check("input[value=smartstore]")
                pg.click("[data-role=m5-check]")
                pg.wait_for_selector("[data-role=m5-checks] .m5-res")
                shot("checked")
                pg.click("[data-role=m5-register]")
                pg.wait_for_selector("[data-role=m5-result]")
                shot("done")
                print("완료:", pg.inner_text("[data-role=m5-done]").replace("\n", " | "))
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
