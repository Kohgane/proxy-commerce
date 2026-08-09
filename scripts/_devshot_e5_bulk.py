"""개발용 스크린샷 — v42 E-5 벌크 정직 요약 + 재시도.
실제 content_script의 kgpRenderRetry/kgpSetStatus를 주입해, 리스팅 벌크바 상태를
BEFORE(성공/실패만) vs AFTER(완료·중복·실패 + 실패 재시도 버튼)로 대조.
"""
import sys, os, glob, re
sys.path.insert(0, os.getcwd())
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")

def _fn(name):
    i = CS.index("function " + name)
    j = CS.index("\n}\n", i) + 2
    return CS[i:j]

TOOLBAR_ID = re.search(r'const KGP_TOOLBAR_ID = "([^"]+)"', CS).group(1)
INJECT = f'const KGP_TOOLBAR_ID = "{TOOLBAR_ID}";\n' + _fn("kgpSetStatus") + "\n" + _fn("kgpRenderRetry")

def bar_html(bar_id, status_text):
    return f"""
    <div id="{bar_id}" style="display:flex;align-items:center;gap:12px;background:#1a1714;color:#f5efe3;
         padding:10px 16px;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.4);max-width:760px">
      <span style="font-weight:700">고가수집기</span>
      <span id="kgp-tb-status-before" style="font-size:13px;color:#c9a24b">{status_text}</span>
    </div>"""

PAGE = f"""<!doctype html><meta charset=utf-8>
<body style="font-family:system-ui;background:#f5efe3;margin:0;padding:24px">
  <div style="font-size:12px;color:#c0392b;font-weight:700;margin:4px 0">BEFORE — 성공/실패만 (중복 뭉뚱그림, 재시도 없음)</div>
  {bar_html('bar-before', '수집 완료 — 성공 14 / 실패 2. 셀러 콘솔 수집 이력에서 확인하세요.')}
  <div style="height:26px"></div>
  <div style="font-size:12px;color:#119a8e;font-weight:700;margin:4px 0">AFTER — 완료·중복·실패 정직 요약 + 실패분 재시도</div>
  <div id="{TOOLBAR_ID}" style="display:flex;align-items:center;gap:12px;background:#1a1714;color:#f5efe3;
       padding:10px 16px;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.4);max-width:760px">
    <span style="font-weight:700">고가수집기</span>
    <span id="kgp-tb-status" style="font-size:13px;color:#c9a24b"></span>
  </div>
<script>
{INJECT}
// AFTER: 실제 코드가 만드는 요약 문구 + 재시도 버튼(kgpRenderRetry).
(function(){{
  var total=16, success=13, dup=1, fail=2;
  var msg = '총 '+total+': 완료 '+success + (dup?' · 중복 '+dup:'') + (fail?' · 실패 '+fail:'') + (fail?' — 아래 ‘재시도’를 누르세요.':'. 셀러 콘솔 수집 이력에서 확인하세요.');
  kgpSetStatus(msg);
  kgpRenderRetry([{{url:'a'}},{{url:'b'}}]);
}})();
</script></body>"""

out = "/tmp/shot_e5.html"
Path(out).write_text(PAGE, encoding="utf-8")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 820, 'height': 260}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + out, wait_until="load")
    p.wait_for_timeout(400)
    print("AFTER status:", p.locator("#" + TOOLBAR_ID + " #kgp-tb-status").inner_text())
    print("retry btn:", p.locator("#kgp-tb-retry").inner_text())
    p.locator("body").screenshot(path="/tmp/shot_e5_panel.png")
    b.close()
print("done")
