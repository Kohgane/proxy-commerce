"""V41-4 레인 게이트 캡처 — 인자: 접두(before/after). 1480·390 전체 페이지."""
import sys, os, threading, time, glob
sys.path.insert(0, os.getcwd()); os.environ["SELLER_CONSOLE_AUTH"]="0"; os.environ["SECRET_KEY"]="devshot"
pre = sys.argv[1]
from src.order_webhook import app
threading.Thread(target=lambda: app.run(port=5414, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe=glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]; bs="/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
os.makedirs("docs/screens/v41_4", exist_ok=True)
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=exe)
    for name,vw in (("m",{"width":390,"height":844}),("d",{"width":1480,"height":900})):
        ctx=b.new_context(viewport=vw, device_scale_factor=2 if name=="m" else 1, is_mobile=name=="m"); p=ctx.new_page()
        p.goto("http://127.0.0.1:5414/lane", wait_until="networkidle")
        if os.path.exists(bs): p.add_style_tag(path=bs)
        p.wait_for_timeout(500)
        p.screenshot(path=f"docs/screens/v41_4/{pre}-{name}-lane-gate.png", full_page=True)
        print(name, "scrollW", p.evaluate("document.documentElement.scrollWidth"), "clientW", p.evaluate("document.documentElement.clientWidth"))
    b.close()
