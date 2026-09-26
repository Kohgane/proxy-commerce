"""F50 캡처 — 팝업 새 버전 배너 · 설치 페이지 안내. before(작업 전 트리)/after(이 트리) 같은 스크립트.

팝업은 실제 popup.html+popup.js에 chrome API만 목(비동기 콜백 — 실크롬과 같게). 서버 최신 버전은 가정값 1.5.160.
사용: python scripts/_devshot_f50.py <before|after> <out_dir>
"""
import json
import os
import sys
from pathlib import Path

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"


def main():
    from playwright.sync_api import sync_playwright
    ext = Path("extensions/chrome-collector")
    ver = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))["version"]
    upd = {"current": ver, "latest": "1.5.160", "newer": True, "download_page": "https://kohganepercentiii.com/seller/extension"}
    stub = """() => { window.chrome = {
      runtime: { id: 'x', getManifest: () => ({version: %s}), sendMessage: (m, cb) => cb && setTimeout(() => cb({}), 0),
                 onMessage: { addListener() {} }, getURL: (p) => p },
      storage: { local: { get: (k, cb) => cb && setTimeout(() => cb(k === 'kgp_update' ? { kgp_update: %s } : {}), 0), set: () => {} },
                 sync: { get: (k, cb) => cb && setTimeout(() => cb({}), 0) }, onChanged: { addListener() {} } },
      tabs: { query: (q, cb) => cb && setTimeout(() => cb([{ url: 'https://world.taobao.com/', id: 1 }]), 0),
              sendMessage: (t, m, cb) => cb && setTimeout(() => cb(null), 0), create: () => {} } }; }""" % (json.dumps(ver), json.dumps(upd))
    html = (ext / "popup.html").read_text(encoding="utf-8")
    for s in ("kgp-sources.js", "kgp-detect.js", "popup.js"):
        html = html.replace(f'<script src="{s}"></script>', "")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        page_html = c.get("/seller/extension").get_data(as_text=True)
    css = "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>" if os.path.exists(BOOTSTRAP) else ""
    css += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    page_html = page_html.replace("</head>", css + "</head>", 1)
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME)
        pg = b.new_page(viewport={"width": 320, "height": 420})
        pg.set_content(html)
        pg.evaluate(stub)
        for s in ("kgp-sources.js", "kgp-detect.js", "popup.js"):
            try:
                pg.add_script_tag(content=(ext / s).read_text(encoding="utf-8"))
            except Exception as exc:
                print("script", s, type(exc).__name__)
        pg.wait_for_timeout(400)
        pg.screenshot(path=f"{OUT}/f50-popup-{TAG}.png")
        pg.close()
        path = f"/tmp/_f50_install_{TAG}.html"
        open(path, "w", encoding="utf-8").write(page_html)
        pg = b.new_page(viewport={"width": 800, "height": 900})
        pg.goto(f"file://{path}")
        pg.wait_for_timeout(300)
        loc = pg.locator("[data-role='ext-update-guide']")
        if loc.count() == 0:
            loc = pg.locator(".pc-status").first
        loc.screenshot(path=f"{OUT}/f50-install-{TAG}.png")
        b.close()
    print("saved", TAG, ver)


if __name__ == "__main__":
    main()
