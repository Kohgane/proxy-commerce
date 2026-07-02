"""개발용 스크린샷 — v42 E-1 확장 옵션 '연결됨 ✓ (계정)'.
options.html을 헤드리스로 열되, chrome.storage(토큰 저장됨)와 fetch(/me→계정)를 스텁해
연결 상태 배너가 '연결됨 ✓ · demo@goga.kr'로 뜨는 것을 촬영.
"""
import sys, os, glob
sys.path.insert(0, os.getcwd())

OPT = os.path.abspath("extensions/chrome-collector/options.html")

STUB = r"""
window.chrome = {
  runtime: { lastError: undefined },
  storage: {
    sync: { get: (keys, cb) => cb({ serverUrl: 'https://kohganepercentiii.com', token: 'kgp_demo_token' }),
            set: (o, cb) => cb && cb(), remove: (k, cb) => cb && cb() },
    local: { get: (keys, cb) => {
                if (String(keys).indexOf('kgp_sources') >= 0) return cb({ kgp_sources: {} });
                return cb({ serverUrl: 'https://kohganepercentiii.com', token: 'kgp_demo_token' });
              },
             set: (o, cb) => cb && cb(), remove: (k, cb) => cb && cb() },
  },
};
window.fetch = (url, opts) => Promise.resolve({
  status: 200,
  json: () => Promise.resolve({ ok: true, email: 'demo@goga.kr', name: '데모 셀러', user_id: 'u1' }),
});
"""

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 640, 'height': 720}, ignore_https_errors=True)
    ctx.add_init_script(STUB)
    p = ctx.new_page()
    p.goto("file://" + OPT, wait_until="load")
    p.wait_for_timeout(800)
    try:
        if p.locator("#connStatus").count():
            print("connStatus:", p.locator("#connStatus").inner_text())
        else:
            print("connStatus: (없음 — 이전 버전)")
    except Exception as e:
        print("connStatus read err:", e)
    p.screenshot(path="/tmp/shot_e1_options.png", full_page=True)
    b.close()
print("done")
