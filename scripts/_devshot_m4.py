"""M4 캡처 — 수집 화면에서 테무 상품 주소로 「미리보기」를 눌렀을 때(서버는 테무 페이지를 못 읽는다).

before(main): 일반 문장. after: 어느 사이트라 안 되는지 + 다음 행동.
사용: python scripts/_devshot_m4.py <before|after> <out_dir>
"""
import os
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
TEMU = "https://www.temu.com/kr/goods.html?goods_id=601099512345"


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    import src.seller_console.views as V
    V._collect_real_draft = lambda url, translate=True: None      # 서버가 못 읽은 상황(실운영과 같은 결과)
    from src.order_webhook import app
    import scripts._devshot_f51 as base
    srv = make_server("127.0.0.1", 5197, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            pg = br.new_page(viewport={"width": 900, "height": 700})
            pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5197") else r.abort())
            pg.goto("http://127.0.0.1:5197/seller/collect", wait_until="domcontentloaded")
            if os.path.exists(base.BOOT):
                pg.add_style_tag(content=open(base.BOOT).read())
            pg.fill("#productUrl", TEMU)
            pg.click("#extractBtn")
            pg.wait_for_selector("#errorAlert:not(.d-none)", timeout=15000)
            pg.wait_for_timeout(300)
            pg.wait_for_timeout(700)                                  # 누른 사람이 보는 그대로(억지 스크롤 없음)
            pg.screenshot(path=f"{OUT}/m4-preview-temu-{TAG}.png")
            seen = pg.evaluate("() => { const r = document.getElementById('errorAlert').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }")
            print(f"[{TAG}] 화면 안에 보임={seen} 문장:", " ".join(pg.inner_text("#errorAlert").split()))
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
