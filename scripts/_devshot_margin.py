"""개발용 스크린샷 — v43-4 마진 계산기 인라인 모달.
편집 페이지에서 '마진 계산기' 클릭 → 모달 오픈(원가·판매가·수수료·배송비 → 마진액/마진율).
"""
import sys, os, glob, threading, time, json, urllib.request
sys.path.insert(0, os.getcwd())

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc
ch._in_memory.clear()
mc.is_connected = lambda *a, **k: True
iid = ch.append(source="extension", url="https://temu.com/g-1.html", title="린넨 3인 소파",
                price="61144", currency="KRW", seller_id="u1")

from src.order_webhook import app
def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    o = {'executable_path': exe}
    if _px: o['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 760, 'height': 640}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto(f"http://127.0.0.1:5098/seller/collect/preview/{iid}", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    # bootstrap JS는 프록시 차단 → 값 채우고 모달을 수동 표시(로직은 실제 openMarginCalc/calcMargin).
    p.evaluate("""() => {
      const cost = (typeof _mcKrw === 'function' ? _mcKrw() : 0) || 61144;
      document.getElementById('mcCost').value = cost;
      document.getElementById('mcSell').value = Math.round(cost * 1.5);
      calcMargin();
      const m = document.getElementById('marginCalcModal');
      m.style.display = 'block'; m.classList.add('show'); m.style.background = 'transparent';
    }""")
    p.wait_for_timeout(400)
    vals = p.evaluate("() => ({cost:mcCost.value, sell:mcSell.value, fee:mcFee.value, ship:mcShip.value, profit:mcProfit.textContent, rate:mcRate.textContent})")
    print("margin:", vals)
    modal = p.locator("#marginCalcModal .modal-content")
    (modal.first if modal.count() else p).screenshot(path="/tmp/shot_margin.png")
    b.close()
print("done")
