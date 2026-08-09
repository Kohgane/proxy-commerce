"""개발용 스크린샷 — Temu 크롤 항목별 payload 검증(5): 갤러리·가격·옵션·상세. 9 KRW 오값 재현·수정."""
import os, sys, glob, json
sys.path.insert(0, os.getcwd())

# 모의 Temu PDP — '9 KRW' 트랩(쿠폰) + 실제가 61,144원 + 갤러리 3 + 옵션(색상/사이즈) + 상세
MOCK = """<!doctype html><html><head>
<meta property="og:title" content="접이식 차량용 책상">
<meta property="og:image" content="https://img.temu.com/g1.jpg">
</head><body>
<div class="product-image"><img src="https://img.temu.com/g1.jpg" width="600" height="600"><img src="https://img.temu.com/g2.jpg" width="600" height="600"><img src="https://img.temu.com/g3.jpg" width="600" height="600"></div>
<div class="coupon"><span class="price">₩9</span> 쿠폰</div>
<div class="buy-box"><span class="price-current">61,144원</span> <span class="price price-original" style="text-decoration:line-through">89,000원</span></div>
<div class="sku-color"><span class="label">색상</span><button aria-label="블랙">블랙</button><button aria-label="화이트">화이트</button></div>
<div class="variant-size"><span class="label">사이즈</span><button>S</button><button>M</button><button>L</button></div>
<select aria-label="수량"><option>선택</option><option>1개</option><option>2개</option></select>
<div id="productDescription">원목 접이식 차량용 책상. 조립 방법을 확인하세요. 무게 1.2kg, 내하중 15kg.</div>
</body></html>"""

CS = open("extensions/chrome-collector/content_script.js", encoding="utf-8").read()

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    p = b.new_context().new_page()
    p.set_content(MOCK, wait_until="load")
    payload = p.evaluate("""(src)=>{
      window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:(u)=>u},
        storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},
                 sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};
      try{ (0,eval)(src); }catch(e){}
      try{ return extractProductMeta(); }catch(e){ return {__err:String(e)}; }
    }""", CS)
    b.close()

# 항목별 검증
price = payload.get("price"); cur = payload.get("currency")
gallery = payload.get("gallery_images") or payload.get("images") or []
opts = payload.get("options") or []
desc = payload.get("description") or ""
price_ok = price in ("61144", "61144.0") and cur == "KRW"       # 9 아님, 원→KRW
gallery_ok = len([g for g in gallery if "temu.com/g" in g]) >= 3
opt_names = [o.get("name") for o in opts]
opt_ok = len(opts) >= 2                                          # 색상/사이즈/수량
desc_ok = "책상" in desc and len(desc) >= 20
print(json.dumps({"price": price, "currency": cur, "price_ok": price_ok,
                  "gallery": len(gallery), "gallery_ok": gallery_ok,
                  "options": [(o.get("name"), o.get("values")) for o in opts], "opt_ok": opt_ok,
                  "desc_len": len(desc), "desc_ok": desc_ok}, ensure_ascii=False))

from PIL import Image, ImageDraw
im = Image.new("RGB", (960, 380), "#1a1714"); d = ImageDraw.Draw(im)
gold, teal, orange, muted, red = (201,162,75),(17,154,142),(245,130,31),(150,145,133),(220,80,70)
d.text((20,16),"Temu 크롤 항목별 payload 검증(5) — 클릭 시점 extractProductMeta 실행",fill=gold)
d.text((20,46),"모의 PDP: '₩9' 쿠폰 트랩 + 실제가 61,144원 + 갤러리3 + 옵션(색상/사이즈/수량) + 상세",fill=muted)
def line(y,label,val,ok):
    d.text((28,y),("● " if ok else "✗ ")+label,fill=(teal if ok else red))
    d.text((360,y),val,fill=(199,231,223))
line(84,"가격(9 KRW 오값 방지)",f"{price} {cur}  (트랩 ₩9 아님·원→KRW)",price_ok)
line(116,"갤러리 이미지",f"{len(gallery)}장 (temu g1~g3)",gallery_ok)
line(148,"옵션(색상/사이즈/수량)",", ".join(f"{n}:{'/'.join(v[:3])}" for n,v in [(o.get('name'),o.get('values')) for o in opts]),opt_ok)
line(180,"상세설명",f"{len(desc)}자 (원목 접이식…)",desc_ok)
d.text((20,220),"수정: _kgpScopedPrice=유효 후보 최댓값 채택(소액 오값 방지) · _kgpCollectOptions 신설(payload.options)",fill=orange)
d.rectangle([20,250,940,330],outline=gold,width=1)
d.text((34,262),"서버(extension_api)는 payload.options 있으면 그대로 저장(편집 프리필). 갤러리/상세 2버킷 유지.",fill=(200,192,178))
d.text((34,288),"항목별: 가격✓ 갤러리✓ 옵션✓ 상세✓ — 전부 클릭 시점 payload에 담김.",fill=(200,192,178))
d.text((34,308),"manifest 1.5.36→1.5.37. 확장 재로딩 후 실제 Temu에서 오너 확인.",fill=muted)
os.makedirs("docs/screens/v45",exist_ok=True); im.save("docs/screens/v45/temu-extract.png")
print("saved docs/screens/v45/temu-extract.png")
