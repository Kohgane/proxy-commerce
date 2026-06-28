"""개발용 스크린샷 — 소싱처 SPA/카테고리 페이지(상품 메타 없음)에서 고가수집기 FAB 노출 여부.

content_script.js를 실제 주입하고, 소싱처에 있는 것처럼 kgpHostAllowed를 강제한 뒤
상품 페이지 휴리스틱이 실패하는 페이지에서 FAB가 뜨는지 확인(before/after).
"""
import sys, os, glob
sys.path.insert(0, os.getcwd())

CS = os.path.abspath("extensions/chrome-collector/content_script.js")
HARNESS = "/tmp/fab_harness.html"
with open(HARNESS, "w", encoding="utf-8") as f:
    f.write(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Temu 카테고리 — 가방</title>
<style>body{{font-family:-apple-system,'Segoe UI',sans-serif;background:#fff;margin:0;padding:40px}}
.hd{{font-size:22px;font-weight:700;color:#fb7701}} .sub{{color:#666;margin-top:8px}}
.note{{margin-top:30px;color:#999;font-size:13px;max-width:640px;line-height:1.6}}</style>
</head><body>
<div class="hd">Temu · 가방 카테고리 (SPA)</div>
<div class="sub">상품 상세 메타(og:type=product)·가격 메타 없음 · URL 패턴도 /dp//item.htm 아님</div>
<div class="note">이 페이지는 소싱처(Temu)의 카테고리/검색/홈처럼 <b>상품 페이지 휴리스틱이 실패</b>하는 화면을 모사합니다.
기존엔 이런 화면에서 고가수집기 버튼이 <b>안 떴습니다</b>(어떤 창은 안 뜸). v38 #4 수정 후엔 소싱처면 <b>항상</b> 노출됩니다.</div>
<script>
  window.chrome = {{
    storage: {{ local: {{ get: (k, cb) => cb({{ kgp_sources: {{}}, kgp_fab_enabled: true }}) }}, onChanged: {{ addListener() {{}} }} }},
    runtime: {{ id: 'devtest', onMessage: {{ addListener() {{}} }}, sendMessage: (m, cb) => cb && cb({{ ok: true, title_ko: '테스트 상품' }}) }}
  }};
</script>
<script src="file://{CS}"></script>
<script>
  // 데모: 실제로는 taobao/1688/temu/amazon 등 소싱처 도메인에서 host 매칭됨.
  kgpHostAllowed = () => true;
  setTimeout(() => {{ try {{ kgpRefresh(); }} catch (e) {{ document.title = 'ERR ' + e.message; }} }}, 300);
</script>
</body></html>""")

out = sys.argv[1] if len(sys.argv) > 1 else "fab"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe, args=["--allow-file-access-from-files"])
    p = b.new_context(viewport={'width': 820, 'height': 420}).new_page()
    p.goto("file://" + HARNESS)
    p.wait_for_timeout(1200)
    has_fab = p.evaluate("() => !!document.getElementById('kgp-collect-fab')")
    p.screenshot(path=f"/tmp/shot_{out}.png")
    b.close()
print(f"/tmp/shot_{out}.png FAB_present={has_fab}")
