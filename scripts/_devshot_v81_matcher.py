"""개발용 스크린샷 — v81 STEP3 소싱처 매처 단일화(팝업≠콘텐츠스크립트 봉인) + 아마존 국가도메인.

실제 kgp-sources.js + kgp-detect.js 로직으로 3상태 배지 렌더:
  ① rakuten 톱 → '소싱처 ✓ · 상품/목록 페이지에서' ② amazon.de/dp → '수집 버튼 표시' ③ 미등록 → '지정 소싱처 아님'.
"""
import os, sys, glob
sys.path.insert(0, os.getcwd())

SRC = open("extensions/chrome-collector/kgp-sources.js", encoding="utf-8").read()
DET = open("extensions/chrome-collector/kgp-detect.js", encoding="utf-8").read()

CASES = [
    ("https://www.rakuten.co.jp/?l2-id=shop_header_logo", "라쿠텐 톱(홈)"),
    ("https://www.amazon.de/dp/B0EXAMPLE", "아마존 독일 상품"),
    ("https://item.rakuten.co.jp/shop/9999/", "라쿠텐 상품"),
    ("https://www.example-shop.io/product/1", "미등록 사이트"),
]

PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<style>
body{font-family:Pretendard,'Noto Sans KR',sans-serif;background:#1A1714;color:#F5EFE3;margin:0;padding:22px}
h1{font-family:'Noto Serif KR',serif;font-size:17px;margin:0 0 4px;color:#C9A24B}
.sub{font-size:12px;color:#b9a08c;margin:0 0 18px}
.card{background:#211d19;border:1px solid #3a332c;border-radius:12px;padding:12px 14px;margin-bottom:10px;width:360px}
.url{font-size:11px;color:#9c8b78;word-break:break-all;margin-bottom:7px}
.badge{font-size:12.5px;padding:7px 10px;border-radius:8px;line-height:1.4}
.on{background:color-mix(in srgb,#119A8E 16%,transparent);color:#5fd0c4;border:1px solid color-mix(in srgb,#119A8E 45%,transparent)}
.hint{background:color-mix(in srgb,#F5821F 14%,transparent);color:#f5a35a;border:1px solid color-mix(in srgb,#F5821F 42%,transparent)}
.off{background:color-mix(in srgb,#c0392b 13%,transparent);color:#e08a80;border:1px solid color-mix(in srgb,#c0392b 40%,transparent)}
.tag{font-size:10.5px;color:#C9A24B;letter-spacing:.04em;text-transform:uppercase;margin-bottom:5px}
</style></head><body>
<h1>소싱처 판정 단일화 (v81 STEP3)</h1>
<p class=sub>팝업·콘텐츠스크립트가 kgp-sources.js 하나로 판정 — rakuten/amazon 국가도메인 흡수 · 쿼리 무시 · 메시지 3분리</p>
<div id=out></div>
<script>SRC_PLACEHOLDER
DET_PLACEHOLDER
function looksCollectable(url){var D=self.KGPDetect;if(!D)return true;if(D.DETAIL_URL_RE.test(url)||D.LIST_URL_RE.test(url))return true;var p='/';try{p=new URL(url).pathname||'/'}catch(e){}return !(p==='/'||p==='');}
var CASES=CASES_PLACEHOLDER;
var out=document.getElementById('out');
CASES.forEach(function(c){
  var url=c[0],tag=c[1];
  var m=self.KGPSources.matchHost(self.KGPSources.hostOf(url),{});
  var cls,txt;
  if(!m){cls='off';txt="여긴 지정 소싱처가 아니에요. '소싱처 관리'에서 추가할 수 있어요.";}
  else if(looksCollectable(url)){cls='on';txt="지정 소싱처 ("+m.label+") — 수집 버튼이 표시돼요";}
  else{cls='hint';txt=m.label+"입니다 (소싱처 ✓). 상품·목록 페이지에서 수집 버튼이 나와요.";}
  var d=document.createElement('div');d.className='card';
  d.innerHTML='<div class=tag>'+tag+'</div><div class=url>'+url+'</div><div class="badge '+cls+'">'+txt+'</div>';
  out.appendChild(d);
});
</script></body></html>"""

import json as _j
html = (PAGE.replace("SRC_PLACEHOLDER", SRC).replace("DET_PLACEHOLDER", DET)
        .replace("CASES_PLACEHOLDER", _j.dumps(CASES, ensure_ascii=False)))
tmp = "/tmp/_v81_matcher.html"
open(tmp, "w", encoding="utf-8").write(html)

from playwright.sync_api import sync_playwright
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe)
    p = b.new_context(viewport={"width": 420, "height": 470}).new_page()
    p.goto("file://" + tmp)
    p.wait_for_timeout(400)
    p.screenshot(path="/tmp/shot_v81_matcher.png", full_page=True)
    # 판정 값도 출력
    vals = p.eval_on_selector_all(".badge", "els=>els.map(e=>e.className.split(' ')[1])")
    print("배지 상태:", vals)
    b.close()
print("캡처: /tmp/shot_v81_matcher.png")
