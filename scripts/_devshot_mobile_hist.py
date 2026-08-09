"""개발용 모바일 스크린샷 — 수집 이력(표본 데이터)을 390px로 캡처(표→카드 대비용)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"

_ROWS = [
    {"id": "it0", "title": "베이직 에코백 캔버스 데일리 숄더백 대용량", "url": "https://taobao.com/p0",
     "domain": "taobao.com", "price": "12,900", "currency": "KRW", "source": "extension",
     "collected_at": "2026-06-28T09:10", "status": "ok", "image_url": "", "extra_json": "{}"},
    {"id": "it1", "title": "프리미엄 가죽 토트백 A4 수납 비즈니스", "url": "https://1688.com/p1",
     "domain": "1688.com", "price": "89,000", "currency": "KRW", "source": "manual",
     "collected_at": "2026-06-28T08:42", "status": "ok", "image_url": "", "extra_json": "{}"},
    {"id": "it2", "title": "캐주얼 크로스백 미니 데일리 여성용", "url": "https://amazon.com/p2",
     "domain": "amazon.com", "price": "23,500", "currency": "KRW", "source": "bulk",
     "collected_at": "2026-06-27T19:05", "status": "archived", "image_url": "", "extra_json": "{}"},
]
import src.seller_console.collect_history_store as ch
ch.list_items = lambda *a, **k: [dict(r) for r in _ROWS]
ch.summary = lambda *a, **k: {"total": 3, "today": 2, "domains": 3,
                              "by_source": {"extension": 1, "bookmarklet": 0, "manual": 1, "bulk": 1}}
ch.distinct_domains = lambda *a, **k: ["taobao.com", "1688.com", "amazon.com"]

from src.order_webhook import app

def run(): app.run(port=5093, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "hist"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, ignore_https_errors=True,
                        is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5093/seller/collect/history', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(600)
    sw = p.evaluate("() => ({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
    # 표(또는 카드) 영역만 — 테이블 컨테이너로 스코프
    loc = p.locator('.table-responsive, .collect-cards').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'), 'page_overflow_x=', sw['s'] - sw['c'])
