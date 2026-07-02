"""개발용 스크린샷 — v41 X-1 리스팅 카드 이미지 귀속.
실제 content_script의 _kgpBestImg를 브라우저에서 실행해, lazy placeholder를 공유하던 두 카드가
BEFORE(raw img.src)=같은 이미지 → AFTER(_kgpBestImg)=각자 data-src로 귀속됨을 시각화.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, re
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
start = CS.index("function _kgpBestImg")
end = CS.index("\n}\n", start) + 2
FN = CS[start:end]

# 두 상품 카드: 둘 다 img.src는 같은 placeholder, data-src만 서로 다름(리스팅 lazy-load 재현).
# 프록시가 외부 이미지를 막으므로 로컬 파일(file://)로 렌더. placeholder 파일명은 lazyload-placeholder(필터 대상).
PLACEHOLDER = "file:///tmp/x1imgs/lazyload-placeholder.png"
A = "file:///tmp/x1imgs/realA.png"
B = "file:///tmp/x1imgs/realB.png"

HTML = """<!doctype html><html><head><meta charset=utf-8>
<style>
body{font-family:'Pretendard',system-ui,sans-serif;background:#f5efe3;margin:0;padding:24px;color:#1a1714}
h2{font-size:15px;margin:0 0 10px}
.row{display:flex;gap:16px;margin-bottom:22px}
.card{background:#fff;border:1px solid #e9ecef;border-radius:12px;padding:12px;width:180px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card img{width:100px;height:100px;object-fit:cover;border-radius:8px;background:#f1f3f5}
.name{font-weight:600;margin-top:8px;font-size:13px}
.tag{font-size:11px;color:#6c757d;margin-top:2px;word-break:break-all}
.bad{color:#c0392b;font-weight:700}.good{color:#119a8e;font-weight:700}
.panel{background:#fff;border-radius:14px;padding:18px;margin-bottom:18px;border:1px solid #eadfcb}
.k{font-size:12px;color:#8a7a55;text-transform:uppercase;letter-spacing:.06em}
</style></head><body>
<div class=panel><div class=k>리스팅 페이지 · 상품 카드 2개 (각자 다른 상품)</div>
<h2>수집기가 어떤 대표 이미지를 상품에 붙이나</h2>
<div class=row id=before></div>
<div class=row id=after></div>
</div>
<script>
%FN%
function mk(src, dataSrc){ const i=document.createElement('img'); i.src=src; i.setAttribute('data-src',dataSrc); return i; }
const cardA = mk('%PH%','%A%');
const cardB = mk('%PH%','%B%');
function card(name, imgUrl, cls, note){
  return `<div class=card><img src="${imgUrl}"><div class=name>${name}</div><div class="tag ${cls}">${note}</div></div>`;
}
// BEFORE: raw img.src(둘 다 placeholder = 같은 이미지 = 엉뚱)
document.getElementById('before').innerHTML =
  '<div style="align-self:center;width:120px" class="bad">BEFORE (raw img.src)</div>' +
  card('상품 A', cardA.src, 'bad', '공유 placeholder') +
  card('상품 B', cardB.src, 'bad', '공유 placeholder → A와 동일');
// AFTER: _kgpBestImg(각자 data-src)
const ia=_kgpBestImg(cardA), ib=_kgpBestImg(cardB);
document.getElementById('after').innerHTML =
  '<div style="align-self:center;width:120px" class="good">AFTER (_kgpBestImg)</div>' +
  card('상품 A', ia, 'good', '자기 이미지 A') +
  card('상품 B', ib, 'good', '자기 이미지 B');
</script></body></html>"""
HTML = HTML.replace('%FN%', FN).replace('%PH%', PLACEHOLDER).replace('%A%', A).replace('%B%', B)

out = "/tmp/shot_x1.html"
Path(out).write_text(HTML, encoding="utf-8")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 780, 'height': 460}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + out, wait_until="networkidle")
    p.wait_for_timeout(1200)
    # 이미지 로드 대기(외부 dummyimage 프록시 차단 가능 → 텍스트/구조가 핵심)
    p.locator(".panel").screenshot(path="/tmp/shot_x1_panel.png")
    b.close()
print("done")
