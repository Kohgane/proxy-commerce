"""Y13-G 5 — 캡처: 드로어 「이미지 번역」 탭의 판촉 사진 줄(제외 · 판촉 + 그래도 넣기). 같은 스크립트를 main 워크트리(전)와
이 브랜치(후)에서 돌린다. 판촉 판정 재료는 T3 계약 픽스처(VRSUK 운영 OCR 글). 사용: python scripts/_devshot_y13g.py OUT TAG"""
import glob, json, os, sys, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT, TAG = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
from src.db import image_translate_queue_pg as Q
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None; ch._in_memory.clear()
from pathlib import Path
FIX = json.loads(Path("tests/fixtures/ko_polish/recent48_2026-09-30.json").read_text(encoding="utf-8"))
PROMO = {"idx": 0, "kind": "gallery", "status": "done", "url": "https://placehold.co/400x400/png?text=promo", "use": True,
         "source_text": FIX["vrsuk_image0"]["source_text"], "target_text": FIX["vrsuk_image0"]["target_text"]}
PLAIN = {"idx": 1, "kind": "gallery", "status": "done", "url": "https://placehold.co/400x400/png?text=plain", "use": True,
         "source_text": "十八纸风琴纸凳 折叠如书", "target_text": "접이식 의자 책처럼 접힘"}
ex = {"title_ko": "1인용 소파 의자", "images": ["https://placehold.co/400x400/png?text=0", "https://placehold.co/400x400/png?text=1"],
      "images_ko": [PROMO, PLAIN]}
iid = ch.append(source="share", url="https://item.taobao.com/item.htm?id=7", seller_id="u1", title="소파", price="10",
                currency="CNY", extra=ex)
from src.order_webhook import app
PORT = 5141
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start(); time.sleep(2)
cookie = app.session_interface.get_signing_serializer(app).dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    c = b.new_context(viewport={'width': 1000, 'height': 1000})
    c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    pg = c.new_page()
    pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
    bs = "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): pg.add_style_tag(path=bs)
    pg.evaluate("typeof kgpEtab === 'function' && kgpEtab('imgko')")
    pg.wait_for_timeout(1500)
    loc = pg.locator("[data-role=imgko-promo]").first
    row = loc.locator("xpath=ancestor::*[contains(@class,'list-group-item') or contains(@class,'kgp-imgko-row')][1]")
    tgt = row if row.count() else loc.locator("xpath=..")
    tgt.scroll_into_view_if_needed()
    tgt.screenshot(path=os.path.join(OUT, f"y13g-promo-{TAG}.png"))
    print(TAG, tgt.inner_text().replace("\n", " / ")[:300])
    b.close()
os._exit(0)
