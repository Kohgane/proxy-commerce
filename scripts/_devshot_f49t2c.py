"""F49-T 2부-c 캡처 — 오너 화면 재현: tier2 잡음 옵션으로 보강된 초안 + 1.5.156 실페이로드(ICE).

입력은 오너가 올린 진단 파일(`fixtures/realpages/diag/…617129397971.html`)의 **실제 추출값**이다.
① 붙여넣기 초안 ② 옛 확장(tier2)이 옵션 4그룹(17/13/12/11)·아이콘 이미지로 보강 → done ③ 티몰 페이지에서 수집(1.5.156 ICE)
그 뒤 드로어 옵션 탭을 찍는다. before(옛 코드)는 ③이 새 행으로 가거나 버려져 초안이 그대로다.
사용: python scripts/_devshot_f49t2c.py <before|after> <out_dir>
"""
import json
import os
import re
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
DIAG = "fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html"
TMALL = "https://detail.tmall.com/item.htm?id=617129397971"
JUNK = [{"name": f"옵션{i}", "values": [f"잡음{i}-{j}" for j in range(n)]} for i, n in enumerate((17, 13, 12, 11))]


def _inline(html):
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    for e in ("src/static/app.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    return html.replace('<script src="/seller/static/seller.js"></script>', js).replace("</head>", css + "</head>", 1)


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    import src.api.extension_api as ext
    from src.order_webhook import app
    from src.collectors.share_collect import collect_input
    from src.seller_console import collect_history_store as S
    os.makedirs(OUT, exist_ok=True)
    t = open(DIAG, encoding="utf-8").read()
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    payload = {k: e.get(k) for k in ("title", "price", "currency", "images", "gallery_images", "options", "skus",
                                     "description", "detail_images", "field_sources", "page_diag")}
    seller = "u-shot-2c"
    iid = collect_input("https://item.taobao.com/item.htm?id=617129397971", seller_id=seller, source="preview",
                        translate=False)["item_id"]
    with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": seller}):
        with app.test_client() as c:
            c.post("/api/v1/collect/enrich", json={"item_id": iid, "options": JUNK,
                                                  "gallery": ["https://img.alicdn.com/tps/icon-a.png"],
                                                  "field_sources": {"options": "tier2", "images": "tier2"}})
            r = c.post("/api/v1/collect/extension", json={"url": TMALL, "translate": False, **payload}).get_json()
            with c.session_transaction() as s:
                s["user_id"] = seller
            html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    rows = S.list_items(seller_id=seller)
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    print(f"[{TAG}] 수집 응답:", {k: r.get(k) for k in ("duplicate", "updated", "draft_pending", "item_id", "message")})
    print(f"[{TAG}] 행 수:", len(rows), "· 초안 옵션:", [(o["name"], len(o["values"])) for o in ex.get("options") or []],
          "· SKU:", len(ex.get("skus") or []), "· 가격:", ex.get("price") or "(없음)")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        open(f"/tmp/_2c_{TAG}.html", "w").write(_inline(html))
        pg = br.new_page(viewport={"width": 760, "height": 1400})
        pg.goto(f"file:///tmp/_2c_{TAG}.html")
        pg.wait_for_timeout(300)
        pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
        pg.wait_for_timeout(200)
        pg.locator('.kgp-esec[data-etab="options"]').first.screenshot(path=f"{OUT}/f49t2c-options-{TAG}.png")
        pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('price'); }")
        pg.wait_for_timeout(150)
        pg.locator('.kgp-esec[data-etab="price"]').first.screenshot(path=f"{OUT}/f49t2c-price-{TAG}.png")
        rc = pg.locator('[data-role="recollect"]')
        if rc.count():
            rc.first.screenshot(path=f"{OUT}/f49t2c-recollect-{TAG}.png")
        br.close()
    print(f"[{TAG}] saved")


if __name__ == "__main__":
    main()
