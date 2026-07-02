"""개발용 스크린샷 — v42 E-3 목록 호버 즉시 수집 버튼.
실제 kgpQuickBtnStyle/KGP_BRIDGE_MINI를 주입해 목록 카드 3개에 상태 렌더:
①기본(숨김) ②hover(썸네일 중앙 '수집' 노출) ③클릭 후 '수집됨 ✓'.
"""
import sys, os, glob
sys.path.insert(0, os.getcwd())
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
def const(name):
    i = CS.index("const " + name + " =")
    j = CS.index(";\n", i) + 1
    return CS[i:j]
def fn(name):
    i = CS.index("function " + name + "(")
    j = CS.index("\n}\n", i) + 2
    return CS[i:j]

INJECT = "const KGP_TOUCH=false;\n" + const("KGP_BRIDGE_MINI") + "\n" + fn("kgpQuickBtnStyle")

PAGE = """<!doctype html><meta charset=utf-8>
<body style="font-family:system-ui;background:#f5efe3;margin:0;padding:24px">
<div style="font-size:13px;font-weight:700;margin-bottom:14px">목록에서 상품 이미지에 마우스 올리면 → 중앙 '수집' 버튼 → 클릭 → '수집됨 ✓'</div>
<div style="display:flex;gap:20px" id="cards"></div>
<script>
%INJECT%
const labels = ['기본 (마우스 벗어남 · 숨김)', '호버 (수집 버튼 노출)', '클릭 후 (수집됨 ✓)'];
const root = document.getElementById('cards');
for (let i=0;i<3;i++){
  const card = document.createElement('div');
  card.style.cssText = 'position:relative;width:200px;background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:10px;box-shadow:0 1px 4px rgba(0,0,0,.06)';
  card.innerHTML = '<div style="width:180px;height:130px;background:#eef1f4;border-radius:8px"></div>'
    + '<div style="font-size:13px;font-weight:600;margin-top:8px">상품 '+(i+1)+'</div>'
    + '<div style="font-size:12px;color:#666">₩'+(12000+i*3000).toLocaleString()+'</div>'
    + '<div style="font-size:10px;color:#999;margin-top:4px">'+labels[i]+'</div>';
  const collected = (i===2);
  const q = document.createElement('div');
  q.className='kgp-card-quick';
  q.innerHTML = '<span style="display:flex;width:14px;height:14px;flex:none">'+KGP_BRIDGE_MINI+'</span><span class="kgp-q-label">'+(collected?'수집됨 ✓':'수집')+'</span>';
  q.style.cssText = kgpQuickBtnStyle(collected);
  if (i===1) q.style.opacity = '1';   // 호버 상태 시뮬레이션
  card.appendChild(q);
  root.appendChild(card);
}
</script></body>""".replace("%INJECT%", INJECT)

out="/tmp/shot_e3.html"; Path(out).write_text(PAGE, encoding="utf-8")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 720, 'height': 280}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + out, wait_until="load")
    p.wait_for_timeout(400)
    n = p.locator(".kgp-card-quick").count()
    print("quick buttons:", n)
    p.locator("body").screenshot(path="/tmp/shot_e3_panel.png")
    b.close()
print("done")
