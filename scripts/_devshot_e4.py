"""개발용 스크린샷 — v42 E-4 전체선택 정확도.
mock 아마존 검색 DOM(24 상품[16 유가+8 무가] + 2 스폰서)을 만들고 실제 _kgpAmazonCards를 실행해
BEFORE(가격 필수 → 16 인식) vs AFTER(ASIN 기준 → 24 인식, 광고 2 제외)를 벌크바 카운트로 대조.
"""
import sys, os, glob
sys.path.insert(0, os.getcwd())
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
def fn(name):
    i = CS.index("function " + name + "(")
    j = CS.index("\n}\n", i) + 2
    return CS[i:j]

INJECT = "\n".join([
    "let _kgpScannedCount=0;",
    "const _KGP_ORIG_PRICE_RE=/x^/; const _KGP_NONPROD_RE=/(recommend|related|footer|review)/i;",
    fn("_kgpInBadRegion"), fn("_kgpAmazonSponsored"), fn("_kgpPrice"),
    fn("_kgpBestImg"), fn("_kgpAmazonCards"),
])

PAGE = """<!doctype html><meta charset=utf-8>
<body style="font-family:system-ui;background:#f5efe3;margin:0;padding:24px">
<div id="results" style="display:none"></div>
<div style="font-size:12px;color:#c0392b;font-weight:700;margin:4px 0">BEFORE — 가격 없는 카드 8개 누락</div>
<div style="display:flex;align-items:center;gap:12px;background:#1a1714;color:#f5efe3;padding:10px 16px;border-radius:12px;max-width:760px">
  <span style="font-weight:700">고가수집기</span><span id="before" style="font-size:13px;color:#c9a24b"></span></div>
<div style="height:22px"></div>
<div style="font-size:12px;color:#119a8e;font-weight:700;margin:4px 0">AFTER — 유효 ASIN 전부 인식 + 광고 정직 제외</div>
<div style="display:flex;align-items:center;gap:12px;background:#1a1714;color:#f5efe3;padding:10px 16px;border-radius:12px;max-width:760px">
  <span style="font-weight:700">고가수집기</span><span id="after" style="font-size:13px;color:#c9a24b"></span></div>
<script>
// mock 아마존 검색 DOM 생성: 16 유가 + 8 무가(모두 유효 ASIN) + 2 스폰서.
const root = document.getElementById('results');
function card(asin, priced, sponsored){
  const el = document.createElement('div');
  el.setAttribute('data-component-type','s-search-result');
  el.setAttribute('data-asin', asin);
  let h = '<a class="a-link-normal" href="https://www.amazon.com/dp/'+asin+'/ref=x"></a>'
        + '<img class="s-image" src="https://m.media-amazon.com/'+asin+'.jpg" alt="Item '+asin+'">'
        + '<h2><span>Item '+asin+'</span></h2>';
  if (priced) h += '<div class="a-price"><span class="a-offscreen">$12.99</span></div>';
  if (sponsored) h += '<span class="s-sponsored-label-text">Sponsored</span>';
  el.innerHTML = h;
  root.appendChild(el);
}
for (let i=0;i<16;i++) card('B0PRC'+String(i).padStart(5,'0'), true, false);
for (let i=0;i<8;i++) card('B0NON'+String(i).padStart(5,'0'), false, false);
for (let i=0;i<2;i++) card('B0SPN'+String(i).padStart(5,'0'), true, true);
%INJECT%
const cards = _kgpAmazonCards();
const scanned = _kgpScannedCount;
const after = cards.length;                       // 24 (광고 2 제외)
const before = cards.filter(c => c.price).length; // 16 (옛 '가격 필수')
document.getElementById('before').textContent = '전체 '+scanned+'개 중 상품 '+before+'개 · '+before+'개 선택';
document.getElementById('after').textContent  = '전체 '+scanned+'개 중 상품 '+after+'개 · 제외 '+(scanned-after)+'(광고 등) · '+after+'개 선택';
</script></body>""".replace("%INJECT%", INJECT)

out = "/tmp/shot_e4.html"; Path(out).write_text(PAGE, encoding="utf-8")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 820, 'height': 240}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + out, wait_until="load")
    p.wait_for_timeout(400)
    print("BEFORE:", p.locator("#before").inner_text())
    print("AFTER:", p.locator("#after").inner_text())
    p.locator("body").screenshot(path="/tmp/shot_e4_panel.png")
    b.close()
print("done")
