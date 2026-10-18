"""Y13-D(오너 2026-10-18) — 캡처: 피샹리 드로어 위쪽(사전검증 4마켓 통과 기록 + 원래 대표 자동 제외) · 큰 사진 다듬기 메모리 글자.

운영 6f9c7ddf 갤러리 기록 그대로(tests/fixtures/y13d_fishangli_gallery.json)를 인메모리에 심고 사전검증 4마켓 통과를 적은 뒤
드로어 위쪽을 찍는다(밖으로 호출 없음). 사용: python scripts/_devshot_y13d.py before|after [OUT]
"""
import glob
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y13d", TAG)
os.makedirs(OUT, exist_ok=True)
FIX = sys.argv[3] if len(sys.argv) > 3 else "tests/fixtures/y13d_fishangli_gallery.json"
MK = ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"]

from src.db import image_translate_queue_pg as Q
Q.state_get = lambda k: {}
Q.state_set = lambda k, v: None
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
ex = json.load(open(FIX, encoding="utf-8"))
ex.pop("_doc", None)
iid = ch.append(source="share", url="https://detail.tmall.com/item.htm?id=851803804374", seller_id="u1", title=ex["title_ko"],
                price="1999", currency="CNY", extra=ex)
from src.order_webhook import app
from src.seller_console import views as V
with app.test_request_context():
    from flask import session
    session["user_id"] = "u1"
    V._pv_mark_ready({"item_id": iid}, MK, {"results": {m: {"ok": True} for m in MK}}, "f1bca5d3")

PORT = 5136
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    for wname, vw in (("desktop", {'width': 1280, 'height': 1100}), ("mobile", {'width': 390, 'height': 900})):
        c = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
        for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css",
                   "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
            if os.path.exists(bs):
                pg.add_style_tag(path=bs)
                break
        pg.wait_for_timeout(700)
        tabs = pg.locator(".kgp-etabs").first
        box = tabs.bounding_box()
        h = int(box["y"]) + 10 if box else 700
        pg.screenshot(path=os.path.join(OUT, f"{TAG}-drawer-top-{wname}.png"), clip={"x": 0, "y": 0, "width": vw["width"], "height": min(h, 1400)})
        lines = []
        for role in ("pv-ready", "pv-ready-pending", "erase-suggest"):
            loc = pg.locator(f"[data-role={role}]")
            lines.append(f"[{role}] " + (loc.first.inner_text().replace("\n", " / ") if loc.count() else "(없음)"))
        with open(os.path.join(OUT, f"{TAG}-drawer-top-{wname}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        c.close()
    b.close()
os._exit(0)
