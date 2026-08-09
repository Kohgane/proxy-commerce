"""개발용 스크린샷 — v81 STEP6 알리 캐러셀 판정 회수(v80 STEP2 배포 확인).

실 content_script 주입 → 버튼 앵커 + 슬라이드 교체 후 생존 판정을 오버레이 배너로.
"""
import glob, os, json
from pathlib import Path
from playwright.sync_api import sync_playwright

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DET = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
STUB = """window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:u=>u,lastError:null,getManifest:()=>({version:'1.5.120'})},storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};"""
ALI = (
 '<!doctype html><html><head><meta charset=utf-8><style>body{font-family:sans-serif;background:#f2ede3;padding:16px}'
 '.list{display:flex;gap:12px}.product-card{position:relative;width:200px;background:#fff;border:1px solid #ddd;border-radius:8px;overflow:hidden}'
 '.swiper img{width:200px;height:200px;object-fit:cover;background:#d8cbb8}.title{font-size:12px;padding:6px}.price{font-weight:700;padding:0 6px 8px;color:#c0392b}'
 '.hover-preview{position:absolute;z-index:2147483643}</style><title>ali search</title></head><body><div class=list>'
 + "".join(
   '<div class="product-card"><a href="/item/100500%d.html"><div class="images-magnifier swiper"><div class="swiper-wrapper">'
   '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S%d_a.jpg"></div></div></div></a>'
   '<div class="hover-preview"></div><div class=title>Foam Roller Massage %d</div><div class=price>US $6.6%d</div></div>' % (i,i,i,i)
   for i in range(1,4))
 + '</div></body></html>')
U = "https://www.aliexpress.com/w/wholesale-roller.html?q=roller"
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY"); o = {"executable_path": exe}
    if px: o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**o)
    pg = b.new_context(viewport={"width": 720, "height": 380}).new_page()
    pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=ALI) if r.request.url.split("#")[0]==U else r.abort())
    pg.goto(U, wait_until="domcontentloaded")
    pg.evaluate("(a)=>{(0,eval)(a[0]);(0,eval)(a[1]);(0,eval)(a[2]);}", [STUB, DET, CS])
    pg.wait_for_timeout(900)
    res = pg.evaluate("""async()=>{const sleep=(m)=>new Promise(r=>setTimeout(r,m));
      const q=document.querySelector('.product-card:first-child .kgp-card-quick');if(!q)return{err:'no-button'};
      const anchor=q.parentElement&&q.parentElement.classList.contains('swiper');
      const z=parseInt(getComputedStyle(q).zIndex||'0',10);
      const track=document.querySelector('.swiper-wrapper');
      track.innerHTML='<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S1_c.jpg"></div>';
      await sleep(400);
      const still=document.querySelector('.product-card:first-child .kgp-card-quick');
      return{anchor,z,survived:!!still,stillCarousel:!!(still&&still.parentElement&&still.parentElement.classList.contains('swiper'))};
    }""")
    print("판정:", json.dumps(res, ensure_ascii=False))
    pg.evaluate("""(r)=>{const d=document.createElement('div');
      d.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#1A1714;color:#F5EFE3;font:13px sans-serif;padding:11px 15px;border-top:3px solid #C9A24B';
      const ok=(r.survived&&r.stillCarousel&&r.z>=2147483644);
      d.innerHTML='<b style=\"color:#C9A24B\">v81 STEP6 · 알리 캐러셀 판정 회수(v80 STEP2 배포 확인)</b><br>'+
        '컨테이너 앵커 '+(r.anchor?'✓':'✗')+' · z-index '+r.z+' (오버레이 …643 위 '+(r.z>=2147483644?'✓':'✗')+') · '+
        '슬라이드 교체 후 버튼 <b style=\"color:'+(ok?'#5fd0c4':'#e08a80')+'\">'+(r.survived?'생존 ✓':'증발 ✗')+'</b> · 캐러셀 잔류 '+(r.stillCarousel?'✓':'✗');
      document.body.appendChild(d);}""", res)
    pg.wait_for_timeout(200)
    pg.screenshot(path="/tmp/shot_v81_carousel.png", full_page=True)
    b.close()
print("캡처: /tmp/shot_v81_carousel.png")
