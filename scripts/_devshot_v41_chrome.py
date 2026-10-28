"""V41-1 캡처 — 1480 데스크톱(대시보드·레인 게이트) + 390 모바일(더보기 시트). 인자: 출력 폴더, 접두, 포트."""
import sys, os, threading, time, glob
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ["SECRET_KEY"] = "devshot"
out, pre, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
from src.order_webhook import app
threading.Thread(target=lambda: app.run(port=port, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
bs = next((p for p in ["/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"] if os.path.exists(p)), None)
def shot(p, path, name, after=None, full=False):
    p.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
    if bs: p.add_style_tag(path=bs)
    p.wait_for_timeout(400)
    if after: after(p); p.wait_for_timeout(450)
    p.screenshot(path=f"{out}/{pre}-{name}.png", full_page=full); print(name)
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"); opts = {"executable_path": exe}
    if px: opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={"width": 1480, "height": 900}, ignore_https_errors=True)
    ctx.add_cookies([{"name": "kgp_lane", "value": "import", "url": f"http://127.0.0.1:{port}"}])
    p = ctx.new_page()
    shot(p, "/seller/dashboard", "d1-dashboard")
    shot(p, "/lane", "d2-lane-gate")
    shot(p, "/seller/dashboard", "d3-sidebar-more-open", after=lambda q: q.evaluate("document.getElementById('sidebarMore') && (document.getElementById('sidebarMore').open = true)"))
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, ignore_https_errors=True)
    m.add_cookies([{"name": "kgp_lane", "value": "rail", "url": f"http://127.0.0.1:{port}"}])
    q = m.new_page()
    shot(q, "/seller/dashboard", "m1-more-sheet", after=lambda r: r.evaluate("toggleSidebar()"))
    shot(q, "/lane", "m2-lane-gate", full=True)
    b.close()
