"""M3-iOS-3 캡처 — 폰 폭 390px.

  empty   : 공유 시트로 빈 내용(src=share) — before: 「공유 내용이 비어서 왔습니다」만 / after: 경로·누가 안 넘겼는지
  clip    : 클립보드가 빈 경우(src=clip)
  install : 화면 A(after: 링크 복사 길 3번 + 캡처 자리 a4)
  make    : 화면 C(after: 공유 시트·클립보드 두 갈래)
사용: python scripts/_devshot_m3ios3.py <before|after> <out_dir>
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

    srv = make_server("127.0.0.1", 5199, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    pages = [("empty", "/seller/collect/share?src=share&text="),
             ("clip", "/seller/collect/share?src=clip&text="),
             ("install", "/seller/guide/iphone"),
             ("make", "/seller/guide/iphone/make")]
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for key, path in pages:
                pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5199") else r.abort())
                resp = pg.goto("http://127.0.0.1:5199" + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(900)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(300)
                pg.screenshot(path=f"{OUT}/m3ios3-{key}-{TAG}.png", full_page=key in ("make", "install"))
                info = pg.evaluate("""() => { const q = s => { const e = document.querySelector(s); return e ? e.innerText : ''; };
                    return [q('[data-role=share-state]'), q('[data-role=share-error]'), q('[data-role=share-raw]')].map(x => x.replace(/\\s+/g, ' ')).join(' | '); }""")
                print(f"[{TAG}/{key}] HTTP {resp.status if resp else '?'} {info}")
                pg.close()
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
