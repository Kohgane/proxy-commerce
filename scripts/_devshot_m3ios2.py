"""M3-iOS 실측 결함 캡처 — 폰 폭 390px.

  fail3 : 단축어가 제목(3자)만 보낸 경우 → 실패 화면(after: 받은 원문 앞 60자 표시)
  split : 단축어가 `title=`·`url=`로 나눠 보낸 경우(before: 링크 못 찾음 / after: 셋을 합쳐 담음)
  make  : 화면 C(before: 「단축어 입력」 7단계 / after: 4동작)
사용: python scripts/_devshot_m3ios2.py <before|after> <out_dir>
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
LINK = "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt"


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

    srv = make_server("127.0.0.1", 5197, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    pages = [("fail3", "/seller/collect/share?text=" + quote("新中式")),
             ("split", "/seller/collect/share?title=" + quote("新中式") + "&url=" + quote(LINK, safe="")),
             ("make", "/seller/guide/iphone/make")]
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for key, path in pages:
                pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5197") else r.abort())
                resp = pg.goto("http://127.0.0.1:5197" + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(900)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(300)
                pg.screenshot(path=f"{OUT}/m3ios2-{key}-{TAG}.png", full_page=key == "make")
                info = pg.evaluate("""() => { const q = s => { const e = document.querySelector(s); return e ? e.innerText : ''; };
                    return [q('[data-role=share-state]'), q('[data-role=share-error]'), q('[data-role=share-raw]')].join(' | '); }""")
                print(f"[{TAG}/{key}] HTTP {resp.status if resp else '?'} {info}")
                pg.close()
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
