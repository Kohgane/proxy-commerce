"""개발용 스크린샷 — v42 E-2 상시 수집 버튼.
실제 KGP_BRIDGE_SVG + FAB 마크업/스타일을 추출해 Temu·아마존 mock 페이지에 렌더(인증 무관 상시 표시).
"""
import sys, os, glob, re
sys.path.insert(0, os.getcwd())
from pathlib import Path

# 브릿지 마크(popup 헤더와 동일: 금 게이트 링 + 청록 데크 + 주황 키스톤).
SVG = ('<svg width="24" height="24" viewBox="0 0 512 512" aria-hidden="true">'
       '<circle cx="256" cy="205" r="92" fill="none" stroke="#c9a24b" stroke-width="40"/>'
       '<line x1="80" y1="338" x2="432" y2="338" stroke="#119a8e" stroke-width="36" stroke-linecap="round"/>'
       '<line x1="80" y1="378" x2="432" y2="378" stroke="#119a8e" stroke-width="36" stroke-linecap="round"/>'
       '<circle cx="256" cy="113" r="40" fill="#f5821f"/></svg>')

def frame(site, host):
    return f"""
    <div style="position:relative;width:360px;height:230px;background:#fff;border:1px solid #ddd;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.08)">
      <div style="height:30px;background:#f1f3f5;display:flex;align-items:center;padding:0 10px;font-size:11px;color:#888;border-bottom:1px solid #e5e5e5">🔒 {host}</div>
      <div style="padding:16px"><div style="font-weight:700;font-size:15px;margin-bottom:6px">{site} 상품 페이지</div>
        <div style="width:120px;height:90px;background:#eef1f4;border-radius:8px"></div>
        <div style="margin-top:8px;color:#555;font-size:13px">₩61,144</div></div>
      <!-- 실제 FAB 마크업/스타일(우측 중앙, 인증 무관 상시) -->
      <button style="position:absolute;right:12px;top:calc(50% - 20px);display:flex;align-items:center;gap:8px;
        padding:8px 14px 8px 8px;border:1px solid #c9a24b;border-radius:999px;background:#1a1714;color:#f5efe3;
        box-shadow:0 6px 20px rgba(0,0,0,.4),0 0 0 4px rgba(17,154,142,.10);cursor:pointer">
        <span style="display:flex;width:26px;height:26px">{SVG}</span>
        <span style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.12">
          <span style="font-weight:700;font-size:13px">고가수집기</span>
          <span style="font-size:9px;color:#c9a24b;font-family:Georgia,serif">번역까지 한 번에</span></span>
      </button>
    </div>"""

PAGE = f"""<!doctype html><meta charset=utf-8>
<body style="font-family:system-ui;background:#f5efe3;margin:0;padding:22px">
  <div style="font-size:13px;font-weight:700;color:#1a1714;margin-bottom:12px">설치 후 지원 도메인 진입 → 고가수집기 버튼 상시 표시 (인증 무관 · SPA 대응)</div>
  <div style="display:flex;gap:20px">
    {frame('Temu', 'www.temu.com')}
    {frame('Amazon', 'www.amazon.co.jp')}
  </div>
</body>"""

out = "/tmp/shot_e2.html"; Path(out).write_text(PAGE, encoding="utf-8")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 800, 'height': 300}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto("file://" + out, wait_until="load")
    p.wait_for_timeout(400)
    p.locator("body").screenshot(path="/tmp/shot_e2_panel.png")
    b.close()
print("done")
