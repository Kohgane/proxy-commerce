"""개발용 스크린샷 — BI 분석을 표본 매출로 캡처(자산은 docs/screens)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"

SAMPLE = {
    "sales_summary": {"today_krw": "184,200", "week_krw": "1,290,500", "month_krw": "5,830,000", "channel_share": {}},
    "top_products": [
        {"sku": "BAG-ECO-01", "qty": 42, "revenue": 541800},
        {"sku": "TOTE-LE-09", "qty": 28, "revenue": 2492000},
        {"sku": "CROSS-MN-03", "qty": 19, "revenue": 446500},
    ],
    "inventory_alerts": {"low_stock": [1, 2, 3], "over_stock": [1]},
    "ad_roi": {"channels": [], "roas_threshold": 1.5},
    "quality": {"unanswered_24h": 2, "delayed_shipping": 1, "refund_rate": 1.4},
}
import src.analytics.bi_engine as bi
bi.BIEngine.build_dashboard = lambda self, **k: SAMPLE

from src.order_webhook import app

def run(): app.run(port=5099, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
out = sys.argv[1] if len(sys.argv) > 1 else 'analytics'
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1180, 'height': 1300}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5099/seller/analytics', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    loc = p.locator('main, .console-content, #content').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
