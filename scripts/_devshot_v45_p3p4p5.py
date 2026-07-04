"""개발용 스크린샷 — v45 P3·P4·P5 확장 오버레이 견고화.

실제 content_script.js를 chromium에 주입해 mock 아마존 검색 페이지에서 동작시킨다.
 - P3: 모든 상품 카드(일반+변형+스폰서)에 '수집' 배지 표시(누락 0), ASIN 없는 미디어는 제외.
 - P4: 벌크바가 상단 중앙 고정.
 - P5: document.body를 통째로 교체(SPA 재렌더)해도 <html> 직속 오버레이(바)가 생존.
"""
import os, glob, json
os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

CS = open("extensions/chrome-collector/content_script.js", encoding="utf-8").read()

import base64
def _img(color, label):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180">'
           f'<rect width="180" height="180" fill="{color}"/>'
           f'<text x="90" y="96" font-size="16" fill="#fff" text-anchor="middle" font-family="sans-serif">{label}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

# mock 아마존 검색 결과: 일반 8 + 변형(data-asin만) 2 + 스폰서 2 + 미디어(ASIN 없음) 2
def card(asin, title, price="$12.99", sponsored=False, comp=True, color="#3b7", label="상품"):
    asin_attr = f'data-asin="{asin}"'
    comp_attr = 'data-component-type="s-search-result"' if comp else ""
    spn = '<span class="s-sponsored-label-text" style="color:#c60;font-size:11px">Sponsored</span>' if sponsored else ""
    pr = f'<span class="a-price"><span class="a-offscreen">{price}</span></span>' if price else ""
    return f"""
    <div {comp_attr} {asin_attr} style="position:relative;display:inline-block;width:210px;min-height:300px;
         margin:8px;padding:12px;border:1px solid #e3e3e3;border-radius:8px;vertical-align:top;background:#fff">
      {spn}
      <img class="s-image" src="{_img(color, label)}"
           style="width:180px;height:180px;object-fit:cover;display:block" alt="{title}">
      <h2><span style="font-size:13px">{title}</span></h2>
      {pr}
      <a class="a-link-normal" href="https://www.amazon.com/dp/{asin}">보기</a>
    </div>"""

cards_html = ""
for i in range(8):
    cards_html += card(f"B0PROD{i:04d}", f"상품 {i+1}", color="#2f8f6f", label="상품")
for i in range(2):
    cards_html += card(f"B0VARI{i:04d}", f"변형레이아웃 {i+1}", price="", comp=False, color="#4a78c0", label="변형")   # data-asin만(가격 없음)
for i in range(2):
    cards_html += card(f"B0SPON{i:04d}", f"스폰서상품 {i+1}", price="$9.99", sponsored=True, color="#c07a2a", label="스폰서")
# 미디어 위젯(ASIN 없음) — 버튼 안 붙어야
cards_html += f"""
    <div data-component-type="s-search-result" style="display:inline-block;width:210px;min-height:300px;margin:8px;padding:12px;
         border:1px dashed #f5a;border-radius:8px;vertical-align:top;background:#fff0f5">
      <img src="{_img('#b0405a','미디어')}" style="width:180px;height:60px;display:block">
      <h2><span>Amazon Music (광고/미디어·ASIN 없음)</span></h2></div>"""

page_html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:16px;background:#eaeded}}
h1{{font-size:18px}}</style></head><body>
<h1>amazon.com — 검색결과 (mock: 상품 12 + 미디어 1)</h1>
<div id="results">{cards_html}</div>
</body></html>"""

# chrome 스텁 + host 허용 override + content_script 주입 스크립트
chrome_stub = """
window.chrome = {
  runtime: { id: 'devshot', sendMessage: function(){}, onMessage:{addListener:function(){}} },
  storage: {
    local: { get: function(keys, cb){ cb({ kgp_sources:{}, kgp_fab_enabled:true }); }, set:function(){} },
    onChanged: { addListener: function(){} }
  },
  i18n: { getMessage: function(){ return ''; } }
};
Object.defineProperty(document, 'hidden', {value:false, configurable:true});
"""

tmp = "/tmp/shot_v45_p3p4p5_page.html"
open(tmp, "w", encoding="utf-8").write(page_html)
os.makedirs("docs/screens/v45", exist_ok=True)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if _px:
        opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={'width': 1000, 'height': 820}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + tmp, wait_until="domcontentloaded")
    p.add_script_tag(content=chrome_stub)
    p.add_script_tag(content=CS)
    # host/hostname 게이트 우회(file:// 페이지라 amazon 아님) — 실제 _kgpAmazonCards(P3 변경분)로 강제.
    p.evaluate("window.kgpHostAllowed = () => true;"
               "window.kgpFindCards = () => (window._kgpAmazonCards ? _kgpAmazonCards() : []);"
               "if (window.kgpRefresh) kgpRefresh();")
    p.wait_for_timeout(700)

    stats = p.evaluate("""() => ({
      badges: document.querySelectorAll('.kgp-card-chk').length,
      bar: !!document.getElementById('kgp-listing-toolbar'),
      barTop: (()=>{ const b=document.getElementById('kgp-listing-toolbar'); if(!b) return null;
                     const r=b.getBoundingClientRect(); return {top:Math.round(r.top), centerish: Math.abs((r.left+r.width/2) - window.innerWidth/2) < 40}; })(),
      barParent: (()=>{ const b=document.getElementById('kgp-listing-toolbar'); return b? b.parentElement.tagName : null; })()
    })""")
    print("주입 결과:", json.dumps(stats, ensure_ascii=False))
    p.screenshot(path="/tmp/shot_v45_p3p4p5_a.png", full_page=False)

    # P5: body 통째 교체(SPA 재렌더) → <html> 직속 바 생존 확인
    survived = p.evaluate("""() => {
      const before = !!document.getElementById('kgp-listing-toolbar');
      document.body.innerHTML = '<h1>SPA 재렌더됨(본문 교체)</h1>';
      const after = !!document.getElementById('kgp-listing-toolbar');   // <html> 직속이라 생존
      return { before, after };
    }""")
    print("P5 body-swap 생존:", json.dumps(survived))
    p.wait_for_timeout(300)
    p.screenshot(path="/tmp/shot_v45_p3p4p5_b.png", full_page=False)
    b.close()

# 합성 캡처: A(배지+바) 위, B(body-swap 후 바 생존) 아래
from PIL import Image, ImageDraw
a = Image.open("/tmp/shot_v45_p3p4p5_a.png").convert("RGB")
bb = Image.open("/tmp/shot_v45_p3p4p5_b.png").convert("RGB")
W = 1000
def fit(im, h):
    r = W / im.width; im2 = im.resize((W, int(im.height*r))); return im2.crop((0,0,W,min(h,im2.height)))
a, bb = fit(a, 560), fit(bb, 200)
band = 42
canvas = Image.new("RGB", (W, band + a.height + band + bb.height + 12), "white")
d = ImageDraw.Draw(canvas)
d.text((14,12), "P3·P4 — 실제 content_script 주입: 모든 상품 카드(일반·변형·스폰서)에 '수집' 배지 + 벌크바 상단중앙 고정", fill=(17,154,142))
canvas.paste(a, (0, band))
y = band + a.height
d.text((14, y+10), "P5 — document.body 통째 교체(SPA 재렌더)해도 <html> 직속 벌크바 생존(깜빡임 방지)", fill=(201,120,40))
canvas.paste(bb, (0, y+band))
canvas.save("docs/screens/v45/p3p4p5-extension.png")
print("saved docs/screens/v45/p3p4p5-extension.png")
