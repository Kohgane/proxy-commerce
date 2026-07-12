"""scripts/_devshot_extract_contract.py — v58 STEP1: 추출 계약 실증(3사이트 real Chromium).

kgp-extractor.js + content_script.js를 실제 Chromium에 로드해 extractProductMeta()를 3 사이트 픽스처
(테무-state·일반몰(JSON-LD)·testpage(og/meta))에서 실행 → title·price·images 계약 확인.

결론(v58): 확장 추출은 title·price·images 정상 — 회귀 없음. 오너 '미수집'의 근원은 북마클릿 엔티티
SyntaxError(v59에서 수리). 이 스크립트는 그 사실을 실 브라우저로 못박고 캡처를 만든다.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.getcwd())

EX = open("extensions/chrome-collector/kgp-extractor.js", encoding="utf-8").read()
CS = open("extensions/chrome-collector/content_script.js", encoding="utf-8").read()

FIXTURES = {
    "generic_mall(JSON-LD)": """<!doctype html><html><head>
<meta property="og:title" content="프리미엄 무선 이어폰 X100">
<meta property="og:image" content="https://mall.example.com/p/main.jpg">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"프리미엄 무선 이어폰 X100","image":["https://mall.example.com/p/1.jpg","https://mall.example.com/p/2.jpg"],"offers":{"@type":"Offer","price":"39000","priceCurrency":"KRW"}}</script>
</head><body><h1>프리미엄 무선 이어폰 X100</h1><div class="price">39,000원</div>
<div class="gallery"><img src="https://mall.example.com/p/1.jpg" width="600" height="600"><img src="https://mall.example.com/p/2.jpg" width="600" height="600"></div></body></html>""",
    "testpage(og/meta)": """<!doctype html><html><head>
<meta property="og:title" content="데모 상품 접이식 차량용 책상">
<meta property="product:price:amount" content="18900"><meta property="product:price:currency" content="KRW">
</head><body><h1>데모 상품 접이식 차량용 책상</h1><div class="price">18,900원</div>
<div class="gallery"><img src="https://demo.example.com/desk1.jpg" width="600" height="600"></div></body></html>""",
    "temu(state-json)": """<!doctype html><html><head></head><body>
<script>window.rawData={store:{goods:{goodsName:"미니 가습기 USB",galleryImages:["https://img.temu.com/a1.jpg","https://img.temu.com/a2.jpg","https://img.temu.com/a3.jpg"],price:{amount:"12900",currency:"KRW"}}}};</script>
<div class="buy-box"><span class="price">12,900원</span></div></body></html>""",
}


def run():
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    out = {}
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        p = b.new_context().new_page()
        for name, html in FIXTURES.items():
            p.set_content(html, wait_until="load")
            r = p.evaluate(
                """(a)=>{const[EX,CS]=a;
                window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:(u)=>u},
                  storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};
                try{(0,eval)(EX);(0,eval)(CS);}catch(e){return{__err:String(e)}}
                try{return extractProductMeta();}catch(e){return{__err:String(e)}}}""",
                [EX, CS],
            )
            out[name] = {
                "title": (r.get("title") or "")[:40],
                "price": r.get("price"),
                "currency": r.get("currency"),
                "images": len(r.get("images") or []),
                "options": len(r.get("options") or []),
                "source": r.get("source"),
            }
        b.close()
    return out


if __name__ == "__main__":
    res = run()
    print(json.dumps(res, ensure_ascii=False, indent=2))
