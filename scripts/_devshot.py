"""개발용 스크린샷 헬퍼 — 샘플 소싱 데이터를 주입해 카드 레이아웃을 캡처(커밋 자산은 docs/screens)."""
import sys, os
sys.path.insert(0, os.getcwd())
import base64, io, os, sys, threading, time, glob
from PIL import Image, ImageDraw

os.environ["SELLER_CONSOLE_AUTH"] = "0"

def _img(w, h, color, label):
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im); d.text((10, 10), label, fill=(255,255,255))
    b = io.BytesIO(); im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

# 일부는 정상 이미지(다양한 비율), 일부는 로드 실패 URL → 깨짐 처리(플레이스홀더 vs 박스 붕괴) 대비가 보이게
_BROKEN = "http://127.0.0.1:9/nope.jpg"  # 연결 거부 → onerror 발동(네이버 핫링크 차단 상황 모사)
SAMPLE = [
    {"title":"베이직 에코백 캔버스 데일리 숄더백 대용량","price":12900,"mall":"스토어A","link":"#","image":_img(600,800,(180,120,90),"세로형")},
    {"title":"프리미엄 가죽 토트백","price":89000,"mall":"스토어B","link":"#","image":_BROKEN},
    {"title":"캐주얼 크로스백 미니","price":23500,"mall":"스토어C","link":"#","image":_img(700,700,(120,150,90),"정사각")},
    {"title":"방수 백팩 노트북 수납 남녀공용","price":45000,"mall":"스토어D","link":"#","image":_BROKEN},
    {"title":"빈티지 메신저백","price":31000,"mall":"스토어E","link":"#","image":_img(800,600,(110,110,110),"가로형2")},
    {"title":"나일론 버킷백","price":18900,"mall":"스토어F","link":"#","image":_img(700,700,(90,140,140),"정사각2")},
]

import src.sourcing.naver_shopping as ns
ns.search_domestic = lambda kw, **k: {"items": SAMPLE, "total": 48213}
ns.is_configured = lambda: True

from src.order_webhook import app

def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
out = sys.argv[1] if len(sys.argv)>1 else 'sourcing'
with sync_playwright() as pw:
    import os as _os
    _px=_os.environ.get('HTTPS_PROXY') or _os.environ.get('HTTP_PROXY')
    _opts={'executable_path':exe}
    if _px: _opts['proxy']={'server':_px,'bypass':'127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width':1280,'height':1400}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5097/seller/sourcing?keyword=에코백', wait_until='networkidle')
    # 에이전트 프록시가 Bootstrap CDN(jsdelivr)을 403 차단 → 로컬 bootstrap.min.css를 주입해
    # 실제 스타일로 캡처(앱 무변경). 없으면: npm install bootstrap@5.3.0 후 node_modules 경로 사용.
    _cands = [
        os.environ.get("DEVSHOT_BOOTSTRAP_CSS", ""),
        "node_modules/bootstrap/dist/css/bootstrap.min.css",
        "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css",
    ]
    for _bs in _cands:
        if _bs and os.path.exists(_bs):
            p.add_style_tag(path=_bs)   # app.css/console.css는 페이지가 이미 로컬 로드
            break
    p.wait_for_timeout(500)
    # 국내 베스트셀러 카드 섹션만 캡처
    loc = p.locator('text=국내에서 팔리는 상품').locator('xpath=ancestor::div[contains(@class,"card")][1]')
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
