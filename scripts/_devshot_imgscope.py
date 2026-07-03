"""개발용 스크린샷 — v43-3 이미지 스코프(판매자 로고 배제 + 갤러리/상세 2버킷).
실제 extractProductMeta를 mock PDP(갤러리 3장 + 판매자 'ALL IN HOME' 로고 + 상세 1장)에 실행.
"""
import sys, os, glob
sys.path.insert(0, os.getcwd())
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
s = CS.index("const _KGP_ORIG_PRICE_RE")
e = CS.index("// 백그라운드 서비스 워커 메시지 리스너")
DEPS = CS[s:e]   # _KGP consts + 가격/영역 헬퍼 + extractProductMeta 전체

G = "file:///tmp/v433img/"
PAGE = f"""<!doctype html><html><head><meta charset=utf-8>
<meta property="og:image" content="{G}g1.png">
<title>린넨 3인 소파</title></head><body>
  <div class="product-gallery">
    <img class="main-image" src="{G}g1.png" alt="소파 정면" width="300" height="300">
    <img src="{G}g2.png" alt="소파 측면" width="300" height="300">
    <img src="{G}g3.png" alt="소파 디테일" width="300" height="300">
  </div>
  <div class="seller-info">
    <img src="{G}allinhome.png" alt="ALL IN HOME" width="300" height="300">
    <span>판매자: ALL IN HOME</span>
  </div>
  <div id="productDescription">
    <img src="{G}detail1.png" alt="상세 컷" width="300" height="300">
  </div>
</body></html>"""

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 760, 'height': 380}, ignore_https_errors=True)
    p = ctx.new_page()
    _pdp = "/tmp/v433img/pdp.html"; Path(_pdp).write_text(PAGE, encoding="utf-8")
    p.goto("file://" + _pdp, wait_until="load")   # file:// 출처라야 file:// 이미지 로드됨
    try:
        p.wait_for_function("Array.from(document.images).every(function(i){return i.complete && i.naturalWidth>0;})", timeout=5000)
    except Exception:
        pass
    p.wait_for_timeout(300)
    result = p.evaluate("(deps) => { " + "eval(deps); const m = extractProductMeta();"
                        " return {images:m.images, gallery:m.gallery_images, detail:m.detail_images, rep:m.image}; }", DEPS)
    print("images:", result["images"])
    print("gallery:", result["gallery"])
    print("detail:", result["detail"])
    logo_in = any("allinhome" in u for u in (result["images"] or []))
    print("SELLER LOGO EXCLUDED:", not logo_in)

    # 결과 패널 렌더
    def names(arr): return [u.split("/")[-1] for u in (arr or [])]
    panel = f"""<!doctype html><meta charset=utf-8><body style="font-family:system-ui;background:#f5efe3;margin:0;padding:22px">
    <div style="font-size:14px;font-weight:700;margin-bottom:12px">v43-3 이미지 스코프 — 판매자 로고 배제 + 갤러리/상세 2버킷</div>
    <div style="display:flex;gap:16px">
      <div style="flex:1;background:#f0fbf9;border:1px solid #a9e0d8;border-radius:12px;padding:14px">
        <div style="color:#119a8e;font-weight:700">갤러리(대표) {len(result['gallery'])}장</div>
        <div style="font-size:12px;margin-top:6px">{', '.join(names(result['gallery']))}</div></div>
      <div style="flex:1;background:#fdf6e3;border:1px solid #e6d9a8;border-radius:12px;padding:14px">
        <div style="color:#8a6d1f;font-weight:700">상세 본문 {len(result['detail'])}장</div>
        <div style="font-size:12px;margin-top:6px">{', '.join(names(result['detail']))}</div></div>
      <div style="flex:1;background:#fff5f5;border:1px solid #f3c0c0;border-radius:12px;padding:14px">
        <div style="color:#c0392b;font-weight:700">제외: 판매자 로고</div>
        <div style="font-size:12px;margin-top:6px">allinhome.png (alt: ALL IN HOME) — 수집 0</div></div>
    </div>
    <div style="margin-top:12px;font-size:12px;color:#555">수집 이미지 전체: {', '.join(names(result['images']))} (로고 없음)</div>
    </body>"""
    p.set_content(panel, wait_until="load"); p.wait_for_timeout(300)
    p.locator("body").screenshot(path="/tmp/shot_imgscope.png")
    b.close()
print("done")
