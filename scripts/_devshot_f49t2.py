"""F49-T 2부 캡처 — 드로어 옵션 탭: 픽스처 SKU를 확장 수집 라우트로 실제 저장 → 드로어 렌더."""
import json, os, sys
TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd()); os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ.pop("DATABASE_URL", None)
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
def _inline(html):
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    for e in ("src/static/app.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    return html.replace('<script src="/seller/static/seller.js"></script>', js).replace("</head>", css + "</head>", 1)
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import src.api.extension_api as ext
from src.order_webhook import app
FIX = __import__("tests.test_f49t2_tmall_ice_sku", fromlist=["x"]).res_of("tests/fixtures/realpages/tmall_1064346880857_ice_min.html")
info = FIX["skuCore"]["sku2info"]; names = {v["vid"]: v["name"] for v in FIX["skuBase"]["props"][0]["values"]}
fen = lambda m: (f"{int(m)//100}.{int(m)%100:02d}" if str(m or "").isdigit() else "")
skus = [{"spec": [names[s["propPath"].split(":")[1]]], "sku_id": s["skuId"], "price": fen(info[s["skuId"]]["price"]["priceMoney"]),
         "currency": "CNY", "reference_price": fen((info[s["skuId"]].get("subPrice") or {}).get("priceMoney")),
         "stock": info[s["skuId"]]["quantity"], "stock_text": info[s["skuId"]]["quantityText"]} for s in FIX["skuBase"]["skus"]]
with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": "u-shot"}):
    with app.test_client() as c:
        d = c.post("/api/v1/collect/extension", json={"url": "https://detail.tmall.com/item.htm?id=1064346880857",
            "title": FIX["item"]["title"], "price": "175.50", "currency": "CNY", "images": FIX["item"]["images"],
            "options": [{"name": "商品规格", "values": list(names.values())}], "skus": skus, "translate": False,
            "field_sources": {"sku": "ice_context"}}).get_json()
        with c.session_transaction() as s: s["user_id"] = "u-shot"
        html = c.get(f"/seller/collect/preview/{d['item_id']}").get_data(as_text=True)
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    open(f"/tmp/_f49t2_{TAG}.html", "w").write(_inline(html))
    pg = br.new_page(viewport={"width": 760, "height": 1400}); pg.goto(f"file:///tmp/_f49t2_{TAG}.html"); pg.wait_for_timeout(300)
    pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
    pg.locator('[data-etab="options"].kgp-esec').first.screenshot(path=f"{OUT}/f49t2-sku-{TAG}.png"); br.close()
print(TAG, "saved")
