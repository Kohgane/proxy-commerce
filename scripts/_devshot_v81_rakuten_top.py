"""개발용 스크린샷 — v81 STEP4 라쿠텐 톱 오수집 차단 + 추천/이력 위젯 블록리스트.

실 content_script 주입 → kgpFindCards → 톱에서 후보 0·버튼 0·skip 사유(recommend-widget) 집계.
"""
import glob, os, json
from pathlib import Path
from playwright.sync_api import sync_playwright

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DET = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
RTOP = Path("fixtures/realpages/rakuten-top.html").read_text(encoding="utf-8")
INJ = """(a)=>{const[det,cs]=a;window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:u=>u,lastError:null,getManifest:()=>({version:'1.5.120'})},storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};(0,eval)(det);(0,eval)(cs);}"""
U = "https://www.rakuten.co.jp/"
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY"); o = {"executable_path": exe}
    if px: o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**o)
    pg = b.new_context(viewport={"width": 900, "height": 620}).new_page()
    def h(r):
        u = r.request.url.split("#")[0]
        if u == U: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=RTOP)
        elif ".jpg" in u: r.fulfill(status=200, content_type="image/svg+xml", body='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#d8cbb8"/></svg>')
        else: r.abort()
    pg.route("**/*", h); pg.goto(U, wait_until="domcontentloaded")
    pg.evaluate(INJ, [DET, CS]); pg.wait_for_timeout(600)
    res = pg.evaluate("""()=>{ const c=kgpFindCards();
      const marks={}; document.querySelectorAll('[data-kgp-skip]').forEach(e=>{const k=e.getAttribute('data-kgp-skip');marks[k]=(marks[k]||0)+1;});
      return {cards:c.length, btns:document.querySelectorAll('.kgp-card-chk,.kgp-card-quick').length, bar:!!document.getElementById('kgp-listing-toolbar'), marks};
    }""")
    print("판정:", json.dumps(res, ensure_ascii=False))
    # 판정 요약 배너를 톱 페이지 위에 오버레이(정직: 실 kgpFindCards 결과값).
    pg.evaluate("""(r)=>{
      const d=document.createElement('div');
      d.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#1A1714;color:#F5EFE3;font:13px Pretendard,sans-serif;padding:12px 16px;border-top:3px solid #C9A24B';
      const ok=(r.cards===0&&r.btns===0);
      d.innerHTML='<b style=\"color:#C9A24B\">v81 STEP4 · 라쿠텐 톱(www.rakuten.co.jp) 판정</b><br>'+
        '저장 후보 <b style=\"color:'+(ok?'#5fd0c4':'#e08a80')+'\">'+r.cards+'</b> · per-tile 수집버튼 <b style=\"color:'+(ok?'#5fd0c4':'#e08a80')+'\">'+r.btns+'</b> · 벌크바 '+(r.bar?'있음':'없음')+
        ' &nbsp;|&nbsp; 제외 사유: '+Object.entries(r.marks).map(([k,v])=>k+' '+v).join(' · ');
      document.body.appendChild(d);
    }""", res)
    pg.wait_for_timeout(200)
    pg.screenshot(path="/tmp/shot_v81_rtop.png", full_page=True)
    b.close()
print("캡처: /tmp/shot_v81_rtop.png")
