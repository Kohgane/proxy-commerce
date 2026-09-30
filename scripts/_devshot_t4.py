"""T4 캡처 — 폰 폭 390px: 카드 → 마켓 선택 → 쿠팡에서 보이는 모습 → 사전검증 → 등록. 매 단계 가로 스크롤 측정.

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
        from src.channel_sync import coupang_uploader as _cu
        from src.uploaders.coupang_options import resolve_option_value

        def _fake_form(product):                    # 캡처용: 쿠팡 카테고리 메타 대신(등록과 같은 SKU 해석)
            return {"ok": True, "category": "78293(캡처용)", "meta_ok": True, "holds": [], "notes": [],
                    "items": [{"label": resolve_option_value(k["spec"][0])["value"] or k["spec"][0],
                               "sell_price_krw": 1690000 + i * 30000, "stock": 5, "confirm": True}
                              for i, k in enumerate(product.get("skus") or [])]}
        _cu.option_form = _fake_form
        import src.services.image_reachability as ir
        ir.check_all = lambda urls, labels=None: {"ok": True, "bad": []}
    except Exception as exc:
        print("dispatcher stub skipped:", exc)

    @app.before_request
    def _as_user():
        from flask import session
        session["user_id"] = "u-m5-shot"

    from src.seller_console import collect_history_store as S
    import json as _j
    _fx = _j.load(open("tests/fixtures/ko_polish/recent48_2026-09-30.json", encoding="utf-8"))
    _vals = _fx["vrsuk_values"][:6]
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=4ebaf1b8", seller_id="u-m5-shot",
                   title="VRSUK 임스 라운지 의자 재고 있음", price="6995.00", currency="CNY",
                   extra={"title": "VRSUK椅", "title_ko": "VRSUK{비즈니스 시리즈} 심플 이임스 리클라이너 오일 왁스 가죽 의자 재고 있음",
                          "price": "6995.00", "currency": "CNY",
                          "images": ["/seller/static/icon-512.png", "/seller/static/icon-192.png", "/seller/static/og-card.png"],
                          "detail_images": ["/seller/static/icon-512.png", "/seller/static/og-card.png", "/seller/static/icon-192.png"],
                          "images_ko": [{"idx": 2, "status": "done", "url": "/seller/static/og-card.png", "use": True,
                                         "source_text": _fx["vrsuk_image0"]["source_text"],
                                         "target_text": _fx["vrsuk_image0"]["target_text"]}],
                          "options": [{"name": "颜色分类", "values": _vals}],
                          "skus": [{"spec": [v], "price": "6995.00", "currency": "CNY", "stock": 5} for v in _vals]})

    srv = make_server("127.0.0.1", 5203, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    B = "http://127.0.0.1:5203"
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
                pg.screenshot(path=f"{OUT}/t4-{key}-{TAG}.png", full_page=full)
                sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                state = pg.evaluate("() => { const e = document.querySelector('[data-role=share-state]'); return e ? e.innerText : ''; }")
                print(f"[{TAG}/{key}] scrollWidth={sw[0]} clientWidth={sw[1]} hscroll={'있음' if sw[0] > sw[1] else '없음'} 상태='{state}'")

            pg.goto(B + "/seller/collect/share?src=share&text=" + quote(SHARE))
            shot("share")
            if TAG == "after":
                pg.goto(B + f"/seller/m/item/{iid}")
                pg.wait_for_selector("[data-role=m5-cp-name]")
                shot("card")
                pg.locator("[data-role=m5-coupang-preview]").screenshot(path=f"{OUT}/t4-preview-{TAG}.png")
                print("미리보기:", pg.inner_text("[data-role=m5-coupang-preview]").replace("\n", " | ")[:300])
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
