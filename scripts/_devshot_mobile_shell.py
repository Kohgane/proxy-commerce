"""순찰 122b-U1 캡처 — 390×844 모바일: 홈·상품·주문·더보기 시트. 인자: 출력 폴더, 접두(before/after), 포트."""
import sys, os, threading, time, glob, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ["SECRET_KEY"] = "devshot"
out, pre, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
from src.order_webhook import app
from src.seller_console import collect_history_store as CH
try:
    CH._in_memory.clear()
except Exception:
    pass
for i, (t, pr, cur) in enumerate([("실크 원피스 흐르는 듯 우아한 민소매 여름 신상", "1058", "CNY"), ("접이식 차량용 노트북 책상 트레이", "89.9", "CNY"), ("무선 블루투스 헤드셋 노이즈캔슬링", "199", "CNY")]):
    try:
        CH.append(source="extension", url=f"https://item.taobao.com/item.htm?id=70000{i}", title=t, image=f"https://picsum.photos/seed/{i}/200",
                  price=pr, currency=cur, seller_id="default")
    except Exception as e:
        print("seed fail", e)
threading.Thread(target=lambda: app.run(port=port, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
bs = next((p for p in ["/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"] if os.path.exists(p)), None)
def shot(p, path, name, after=None):
    p.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
    if bs: p.add_style_tag(path=bs)
    p.wait_for_timeout(400)
    if after: after(p); p.wait_for_timeout(450)
    sw = p.evaluate("document.documentElement.scrollWidth"); cw = p.evaluate("document.documentElement.clientWidth")
    p.screenshot(path=f"{out}/{pre}-{name}.png"); print(name, "scrollW", sw, "clientW", cw)
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"); opts = {"executable_path": exe}
    if px: opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, ignore_https_errors=True)
    p = ctx.new_page()
    shot(p, "/seller/dashboard", "1-home")
    shot(p, "/seller/collect/history", "2-items")
    shot(p, "/seller/orders", "3-orders")
    shot(p, "/seller/orders", "4-more-sheet", after=lambda q: q.evaluate("toggleSidebar()"))
    b.close()
