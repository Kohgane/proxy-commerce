"""T1/T2 캡처 — 폰 폭 390px.

  card : M5 등록 카드(VRSUK 행 재현) — 쿠팡 상품명 before 「… 재고 있음」 / after 정리
  admin: 관리자 「번역 정리 규칙」 화면 + 한 줄 확인(棕红[Oilwaxed防水油蜡半皮]带踏 海外特供) — after만(새 화면)
사용: python scripts/_devshot_t1.py <before|after> <out_dir>
"""
import json
import os
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    import scripts._devshot_f51 as base
    fx = json.load(open("tests/fixtures/ko_polish/recent48_2026-09-30.json", encoding="utf-8"))

    @app.before_request
    def _as_admin():
        from flask import session
        session["user_id"], session["user_role"] = "owner", "admin"

    from src.seller_console import collect_history_store as S
    vals = fx["vrsuk_values"]
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=4ebaf1b8", seller_id="owner",
                   title="VRSUK{비즈니스 시리즈} 심플 이임스 리클라이너 오일 왁스 가죽 Eames 사무용 회전 승강 단일 의자 재고 있음",
                   price="6995.00", currency="CNY",
                   extra={"title": "VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames办公旋转升降现货单椅",
                          "title_ko": fx["titles"][1][2], "price": "6995.00", "currency": "CNY",
                          "images": ["/seller/static/icon-512.png", "/seller/static/icon-192.png"],
                          "options": [{"name": "颜色分类", "values": vals}],
                          "skus": [{"spec": [v], "price": "6995.00", "currency": "CNY", "stock": 5} for v in vals]})
    srv = make_server("127.0.0.1", 5202, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    B = "http://127.0.0.1:5202"
    pages = [("card", f"/seller/m/item/{iid}")]
    if TAG == "after":
        pages.append(("admin", "/seller/admin/ko-polish"))
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
            pg = ctx.new_page()
            for key, path in pages:
                pg.goto(B + path, wait_until="domcontentloaded")
                if key == "admin":
                    pg.fill("#kpSample", vals[0])
                    pg.click("form:has(#kpSample) button[type=submit]")
                    pg.wait_for_load_state("domcontentloaded")
                pg.wait_for_timeout(500)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(250)
                pg.screenshot(path=f"{OUT}/t1-{key}-{TAG}.png", full_page=key == "admin")
                cp = pg.evaluate("() => { const e = document.querySelector('[data-role=m5-coupang-name]'); return e ? e.innerText : ''; }")
                tr = pg.evaluate("() => { const e = document.querySelector('[data-role=kp-trial]'); return e ? e.innerText : ''; }")
                sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                print(f"[{TAG}/{key}] hscroll={'있음' if sw[0] > sw[1] else '없음'} 쿠팡명='{cp}' 확인='{tr.replace(chr(10), ' | ')}'")
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
