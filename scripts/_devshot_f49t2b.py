"""F49-T 2부-b 캡처 — **오너 업로드 실페이지**(수행방패 617129397971)를 그 트리의 실추출기로 읽고,
그 결과(가격·옵션·SKU)를 확장 수집 라우트로 저장한 뒤 드로어 옵션 탭을 찍는다.

before = 수리 전 트리(ICE 래퍼를 못 읽음) · after = 이 트리. 같은 스크립트.
확장 격리 월드는 페이지 전역을 못 보므로 전역을 지우고 추출한다(스크립트 텍스트 경로 = 실경로).
사용: python scripts/_devshot_f49t2b.py <before|after> <out_dir>
"""
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
SNAP = "/home/user/proxy-commerce/fixtures/realpages/diag/kgp-snapshot-detail-tmall-com-item-htm-id-617129397971.html"
URL = "https://detail.tmall.com/item.htm?id=617129397971"


def _inline(html):
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    for e in ("src/static/app.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        if os.path.exists(e):
            css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    return html.replace('<script src="/seller/static/seller.js"></script>', js).replace("</head>", css + "</head>", 1)


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    import src.api.extension_api as ext
    from src.order_webhook import app
    page_html = open(SNAP, encoding="utf-8", errors="ignore").read()
    ex = open("extensions/chrome-collector/kgp-extractor.js", encoding="utf-8").read()
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        pg = br.new_page()
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=page_html)
                 if r.request.resource_type == "document" else r.abort())
        pg.goto(URL, wait_until="domcontentloaded")
        pg.evaluate("() => { try { delete window.__ICE_APP_CONTEXT__; } catch (e) {} window.__ICE_APP_CONTEXT__ = undefined; }")
        pg.add_script_tag(content=ex)
        m = pg.evaluate("() => window.kgpExtractProduct({pageType: 'single'})")
        pg.close()
        print(f"[{TAG}] price={m.get('price')!r} skus={len(m.get('skus') or [])} "
              f"options={[(o['name'], len(o['values'])) for o in m.get('options') or []]} sku_src={m['field_sources'].get('sku')}")
        with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": "u-shot"}):
            with app.test_client() as c:
                d = c.post("/api/v1/collect/extension", json={
                    "url": URL, "title": m.get("title"), "price": m.get("price"), "currency": m.get("currency"),
                    "images": m.get("images"), "options": m.get("options"), "skus": m.get("skus") or [],
                    "translate": False, "field_sources": m.get("field_sources")}).get_json()
                with c.session_transaction() as s:
                    s["user_id"] = "u-shot"
                html = c.get(f"/seller/collect/preview/{d['item_id']}").get_data(as_text=True)
        path = f"/tmp/_f49t2b_{TAG}.html"
        open(path, "w", encoding="utf-8").write(_inline(html))
        pg = br.new_page(viewport={"width": 760, "height": 1600})
        pg.goto(f"file://{path}")
        pg.wait_for_timeout(300)
        pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
        pg.locator('[data-etab="options"].kgp-esec').first.screenshot(path=f"{OUT}/f49t2b-drawer-{TAG}.png")
        br.close()
    print(TAG, "saved")


if __name__ == "__main__":
    main()
