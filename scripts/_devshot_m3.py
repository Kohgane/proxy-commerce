"""M3 캡처 — 아이폰 단축어가 여는 주소(/seller/collect/share?text=<타오바오 공유 글>) · 폰 폭 390px.

before(main): 담으면 편집 드로어로 튕긴다(제목만 있는 초안). after: 결과 화면 + 안내 페이지.
사용: python scripts/_devshot_m3.py <before|after> <out_dir>
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


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.collectors import link_diag
    link_diag.resolve_short_link = lambda url: {"ok": False, "reason": "offline"}   # 샌드박스는 e.tb.cn에 못 나간다
    from src.order_webhook import app
    import scripts._devshot_f51 as base
    srv = make_server("127.0.0.1", 5198, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    pages = [("share", "/seller/collect/share?text=" + quote(SHARE))]
    if TAG == "after":
        pages.append(("guide", "/seller/guide/phone"))
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for key, path in pages:
                pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5198") else r.abort())
                pg.goto("http://127.0.0.1:5198" + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(1200)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(400)
                print(f"[{TAG}/{key}] 최종 주소:", pg.url.replace("http://127.0.0.1:5198", ""))
                shot = f"{OUT}/m3-{key}-{TAG}.png"
                if key == "guide":
                    pg.screenshot(path=shot, full_page=True)
                else:
                    pg.screenshot(path=shot)
                pg.close()
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
