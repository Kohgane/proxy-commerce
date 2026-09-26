"""F51 캡처 — 편집 화면 「쿠팡 필수 옵션」 블록, 수행방패 ICE SKU 10개(오너 실물 최소 픽스처).

쿠팡 쪽은 `_api_request`만 목(카테고리·메타·출고지). 판매가는 **실제 식**(`calc_sell_price` — 쿠팡 수수료
실측 10.8%, 환율은 앱 기본값)으로 SKU마다 낸다. 용어집은 **실제 용어집 그대로**(가정 값 없음) —
그래서 after 화면은 「색상 값 10개가 용어집에 없습니다」 보류를 보여 준다(그게 지금 사실이다).
사용: python scripts/_devshot_f51.py <before|after> <out_dir>
"""
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
SHIP = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "22796911", "COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": "25099966",
    "COUPANG_RETURN_ZIP_CODE": "06236", "COUPANG_RETURN_ADDRESS": "서울", "COUPANG_RETURN_CHARGE_NAME": "CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-1", "COUPANG_DELIVERY_COMPANY_CODE": "CJGLS", "COUPANG_IMAGE_SCREEN": "0",
}
os.environ.update(SHIP)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
META = {"attributes": [
    {"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED", "groupNumber": "NONE"},
    {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER", "basicUnit": "개", "usableUnits": ["개"],
     "exposed": "EXPOSED", "groupNumber": "NONE"}], "noticeCategories": [], "requiredDocumentNames": []}
FIX = "/home/user/proxy-commerce/tests/fixtures/realpages/tmall_617129397971_ice_min.html"


def _api(self, method, path, data=None):
    if "categorization/predict" in path:
        return {"data": {"predictedCategoryId": "63955"}}
    if "category-related-metas" in path:
        return {"data": META}
    if "shipping-place/outbound" in path:
        return {"data": [{"outboundShippingPlaceCode": "25099966", "addressType": "OVERSEA"}]}
    return {"code": "SUCCESS", "data": None}


def _inline(html):
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    for e in ("src/static/app.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    return html.replace('<script src="/seller/static/seller.js"></script>', js).replace("</head>", css + "</head>", 1)


def _product():
    import json
    t = open(FIX, encoding="utf-8").read()
    i = t.index("var b = {") + 8
    dec = json.JSONDecoder()
    res = dec.raw_decode(t[i:])[0]["loaderData"]["home"]["data"]["res"]
    vals = {v["vid"]: v for v in res["skuBase"]["props"][0]["values"]}
    info = res["skuCore"]["sku2info"]
    skus = [{"spec": [vals[s["propPath"].split(":")[1]]["name"]], "sku_id": s["skuId"],
             "price": f"{int(info[s['skuId']]['price']['priceMoney']) / 100:.2f}", "currency": "CNY",
             "stock": info[s["skuId"]]["quantity"], "image": vals[s["propPath"].split(":")[1]]["image"]}
            for s in res["skuBase"]["skus"]]
    return {"title": res["item"]["title"], "price": 29.9, "currency": "CNY", "sku": "617129397971",
            "images": res["item"]["images"], "origin": "중국",
            "options": [{"name": "颜色分类", "values": [v["name"] for v in res["skuBase"]["props"][0]["values"]]}],
            "skus": skus}


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.uploaders.coupang_uploader import CoupangUploader
    os.makedirs(OUT, exist_ok=True)
    prod = _product()
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title=prod["title"], price="29.90",
                   currency="CNY", source="extension", seller_id="u-shot",
                   extra={"options": prod["options"], "images": prod["images"], "skus": prod["skus"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    with patch.object(CoupangUploader, "_api_request", _api), \
            patch("src.seller_console.market_cred_view.resolve_upload_account", lambda: ""):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u-shot"
            html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
            d = c.post("/seller/collect/coupang/options", json={"product": prod}).get_json()
    print(f"[{TAG}] holds:", d.get("holds"))
    print(f"[{TAG}] multi:", d.get("multi"), "items:", len(d.get("items") or []),
          "prices:", sorted({i.get("sell_price_krw") for i in d.get("items") or []}))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        open(f"/tmp/_f51_{TAG}.html", "w").write(_inline(html))
        pg = br.new_page(viewport={"width": 760, "height": 1200})
        pg.goto(f"file:///tmp/_f51_{TAG}.html")
        pg.wait_for_timeout(300)
        pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
        pg.evaluate("(d) => kgpRenderCoupangOptions(d)", d)
        pg.wait_for_timeout(200)
        pg.locator('[data-role="coupang-options"]').screenshot(path=f"{OUT}/f51-options-{TAG}.png")
        br.close()
    print(f"[{TAG}] saved")


if __name__ == "__main__":
    main()
