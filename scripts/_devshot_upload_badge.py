"""개발용 스크린샷 — v44-1 업로드 성공 표식.
(A) 결과 모달: 마켓별 뱃지(쿠팡 ✓·스스 ✓·11번가 ✗) + 실패 재시도.
(B) 수집이력 행: '등록됨 · 쿠팡·스스' 영구 뱃지.
"""
import sys, os, glob, threading, time
sys.path.insert(0, os.getcwd())

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc
ch._in_memory.clear()
mc.is_connected = lambda *a, **k: True
iid = ch.append(source="extension", url="https://temu.com/g-1.html", title="린넨 3인 소파 · 아이보리",
                price="61144", currency="KRW", seller_id="u1",
                extra={"uploaded": [{"market": "coupang", "market_label": "쿠팡", "external_url": "https://c/1"},
                                    {"market": "smartstore", "market_label": "스마트스토어", "external_url": "https://s/2"}]})

from src.order_webhook import app
def run(): app.run(port=5099, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

MOCK_RESULT = {
  "ok": True,
  "result": {"product_url": "", "total": 3, "succeeded": 2, "queued": 0, "failed": 1, "results": [
    {"market": "coupang", "market_label": "쿠팡", "success": True, "external_url": "https://coupang.com/p/1", "external_product_id": "CP123", "message": "등록 성공"},
    {"market": "smartstore", "market_label": "스마트스토어", "success": True, "external_url": "https://smartstore.naver.com/p/2", "message": "등록 성공"},
    {"market": "elevenst", "market_label": "11번가", "success": False, "message": "API 키 미설정", "error_code": "token_missing", "hint": "마켓 연동에서 11번가 키 입력"},
  ]},
}

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    o = {'executable_path': exe}
    if _px: o['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 900, 'height': 760}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()

    # (A) 결과 모달 렌더(renderUploadResults 실제 호출)
    p.goto(f"http://127.0.0.1:5099/seller/collect/preview/{iid}", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(400)
    import json as _j
    p.evaluate("""(d) => {
      renderUploadResults(d);
      // 결과 컨테이너를 body 최상단으로 옮겨 깔끔히 캡처(숨겨진 모달 step 밖으로).
      const el = document.getElementById('uploadResults');
      el.style.cssText = 'display:block;background:#fff;padding:16px;max-width:600px;border-radius:12px';
      document.body.prepend(el);
      document.body.style.background = '#f5efe3';
    }""", MOCK_RESULT)
    p.wait_for_timeout(300)
    ur = p.locator("#uploadResults")
    ur.screenshot(path="/tmp/shot_upresult.png")
    print("result html has badge:", "등록됨" in ur.inner_html(), "retry:", "재시도" in ur.inner_html())

    # (B) 수집이력 행의 등록됨 뱃지
    p.goto("http://127.0.0.1:5099/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(400)
    row = p.locator("tr", has_text="린넨 3인 소파")
    (row.first if row.count() else p.locator("body")).screenshot(path="/tmp/shot_uprow.png")
    b.close()
print("done")
