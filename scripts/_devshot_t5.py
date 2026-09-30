"""T5 캡처 — 폰 폭 390px(단축어 최종 고정: 동작 셋·v=2·text+clip 서버 판단).

  oldver  : v 없는 옛 단축어로 담기 → after: 「단축어가 구버전입니다」 + 재설치 버튼
  empty2  : v=2, 공유 글·클립보드 둘 다 빔
  clip2   : v=2, 공유 글엔 제목만 + 클립보드에 링크 → 클립보드 링크로 담김(경로: 클립보드는 실패 때만 표시)
  install : 화면 A(4단계)   make: 화면 C(동작 셋 + 캡처 자리 3 + 버전별 도착 수)
사용: python scripts/_devshot_t5.py <before|after> <out_dir>
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
    link_diag.resolve_short_link = lambda url: ({"ok": True, "item_id": "812345678901", "price": "", "currency": "", "reason": ""}
                                                if "ClipOnly" in url else {"ok": False, "reason": "offline"})
    from src.order_webhook import app
    import scripts._devshot_f51 as base

    @app.before_request
    def _as_admin():                        # 캡처용: 화면 C는 관리자만
        from flask import session
        session["user_id"], session["user_role"] = "owner", "admin"

    srv = make_server("127.0.0.1", 5201, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    SH = ("【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356 "
          "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」 点击链接直接打开")
    pages = [("oldver", "/seller/collect/share?text=" + quote(SH, safe="")),
             ("empty2", "/seller/collect/share?v=2&text=&clip="),
             ("clip2", "/seller/collect/share?v=2&text=" + quote("新中式") + "&clip=" + quote("https://e.tb.cn/h.9ClipOnlyAbCd?tk=ClipTok9", safe="")),
             ("install", "/seller/guide/iphone"),
             ("make", "/seller/guide/iphone/make")]
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for key, path in pages:
                pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5201") else r.abort())
                resp = pg.goto("http://127.0.0.1:5201" + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(900)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(300)
                pg.screenshot(path=f"{OUT}/t5-{key}-{TAG}.png", full_page=key in ("make", "install"))
                info = pg.evaluate("""() => { const q = s => { const e = document.querySelector(s); return e ? e.innerText : ''; };
                    return [q('[data-role=share-state]'), q('[data-role=share-oldver]'), q('[data-role=share-error]'), q('[data-role=share-raw]')].map(x => x.replace(/\\s+/g, ' ')).join(' | '); }""")
                print(f"[{TAG}/{key}] HTTP {resp.status if resp else '?'} {info}")
                pg.close()
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
