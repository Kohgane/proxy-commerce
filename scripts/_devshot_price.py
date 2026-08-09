"""개발용 스크린샷 — v42 1-1 가격 클릭 시점 추출.
mock Temu PDP(렌더 '61,144원' + 스테일 og:price 0.00 USD)에서 실제 확장 가격 함수를 실행해
BEFORE(og:price 우선 → 0.00 USD) vs AFTER(렌더 DOM 현재가 → 61,144 KRW)를 대조.
추가로 61,144/KRW로 실제 편집 드로어를 촬영(오너 요청: 드로어에 61,144 KRW).
"""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time, json, urllib.request
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
# 가격 관련 함수 블록 추출(_KGP_ORIG_PRICE_RE ~ _kgpScopedPrice 끝).
s1 = CS.index("const _KGP_ORIG_PRICE_RE")
s2 = CS.index("function _kgpScopedPrice")
e2 = CS.index("\n}\n", s2) + 2
FNS = CS[s1:e2]

MOCK = """<!doctype html><html><head><meta charset=utf-8>
<meta property="product:price:amount" content="0.00">
<meta property="product:price:currency" content="USD">
<style>body{font-family:system-ui;margin:0}</style></head>
<body>
  <div class="recommend"><span class="price">$9.99</span></div>
  <div class="goods-detail">
    <h1>접이식 차량용 책상 · 폴딩 테이블</h1>
    <div class="pdp-buy">
      <span class="ProductPrice_currentPrice">61,144원</span>
      <del class="price-original">80,000원</del>
      <button>장바구니</button>
    </div>
  </div>
</body></html>"""

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc
ch._in_memory.clear()
mc.is_connected = lambda *a, **k: True

from src.order_webhook import app
def run(): app.run(port=5093, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

# 실제 확장 로직으로 수집(61,144/KRW) → 편집 드로어에서 확인.
req = urllib.request.Request("http://127.0.0.1:5093/api/v1/collect/extension",
    data=json.dumps({"url": "https://www.temu.com/kr/g-601150655669129.html",
                     "title": "접이식 차량용 책상 · 폴딩 테이블",
                     "price": "61144", "currency": "KRW"}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
resp = json.loads(urllib.request.urlopen(req).read())
item_id = resp.get("item_id")
print("collect:", resp.get("ok"), item_id)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 820, 'height': 560}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()

    # ── 추출 before/after: mock Temu DOM에서 실제 함수 실행 ──
    p.set_content(MOCK)
    result = p.evaluate("""(fns) => {
      eval(fns);
      const getMeta = (prop) => { const el=document.querySelector(`meta[property="${prop}"],meta[name="${prop}"]`); return el?el.getAttribute('content')||'':''; };
      const scoped = _kgpScopedPrice();
      // AFTER(신): scoped 우선 → meta → (본문 생략)
      let ap=scoped.price, ac=scoped.currency||'';
      if(!ap){ const a=getMeta('product:price:amount'); if(a){ap=a;ac=(getMeta('product:price:currency')||'').toUpperCase();} }
      // BEFORE(구): og:price 우선 + USD 기본값
      let bp = getMeta('product:price:amount') || (getMeta('product:price:amount')? '' : scoped.price);
      let bc = getMeta('product:price:currency') || scoped.currency || 'USD';
      return { rendered:'61,144원', after:{price:ap,currency:ac}, before:{price:bp,currency:bc} };
    }""", FNS)
    panel = ("""<!doctype html><meta charset=utf-8><body style="font-family:system-ui;background:#f5efe3;margin:0;padding:24px;color:#1a1714">
    <div style="background:#fff;border:1px solid #eadfcb;border-radius:14px;padding:20px;max-width:720px">
      <div style="font-size:12px;color:#8a7a55;text-transform:uppercase;letter-spacing:.06em">Temu 책상 PDP · 화면에 렌더된 가격</div>
      <div style="font-size:26px;font-weight:800;margin:6px 0 16px">RENDERED_PRICE</div>
      <div style="display:flex;gap:16px">
        <div style="flex:1;background:#fff5f5;border:1px solid #f3c0c0;border-radius:12px;padding:14px">
          <div style="color:#c0392b;font-weight:700">BEFORE (og:price 우선)</div>
          <div style="font-size:22px;font-weight:800;margin-top:8px">BEFORE_VAL</div>
          <div style="font-size:12px;color:#6c757d">스테일 메타 + USD 기본값</div>
        </div>
        <div style="flex:1;background:#f0fbf9;border:1px solid #a9e0d8;border-radius:12px;padding:14px">
          <div style="color:#119a8e;font-weight:700">AFTER (렌더 DOM 현재가)</div>
          <div style="font-size:22px;font-weight:800;margin-top:8px">AFTER_VAL</div>
          <div style="font-size:12px;color:#6c757d">₩/원→KRW, 추천·취소선 제외</div>
        </div>
      </div>
    </div></body>"""
      .replace("RENDERED_PRICE", result["rendered"])
      .replace("BEFORE_VAL", (result["before"]["price"] or "0.00") + " " + (result["before"]["currency"] or ""))
      .replace("AFTER_VAL", (result["after"]["price"] or "-") + " " + (result["after"]["currency"] or "")))
    print("extract before:", result["before"], "after:", result["after"])
    p.set_content(panel)
    p.wait_for_timeout(300)
    p.locator("div").first.screenshot(path="/tmp/shot_price_extract.png")

    # ── 실제 편집 드로어: 61,144 KRW 표시 ──
    p.goto(f"http://127.0.0.1:5093/seller/collect/preview/{item_id}?drawer=1", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(600)
    p.screenshot(path="/tmp/shot_price_drawer.png", full_page=True)
    b.close()
print("done")
