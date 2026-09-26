"""F48-c 캡처 — 편집 화면 「쿠팡 필수 옵션」(before=main에는 블록 없음 / after=멈춤 → 채움 후 통과).

쿠팡 쪽은 `_api_request`만 목(메타·출고지). 블록 내용은 **실제 라우트 응답**을 화면 렌더 함수가 그린 것이다.
사용: python _devshot_f48c.py <before|after> <out_dir>
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
COLORS = ["黑色", "白色", "红色", "蓝色", "绿色", "黄色", "粉色", "紫色", "灰色", "棕色", "橙色", "米色", "卡其色"]
META = {"attributes": [
    {"attributeTypeName": "적용모델", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED", "groupNumber": "NONE"},
    {"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED", "groupNumber": "NONE"},
    {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER", "basicUnit": "개", "usableUnits": ["개"],
     "exposed": "EXPOSED", "groupNumber": "NONE"}], "noticeCategories": [], "requiredDocumentNames": []}


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
    css += "<style>" + open("src/static/app.css").read() + "</style>"
    for e in ("src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    return html.replace('<script src="/seller/static/seller.js"></script>', js).replace("</head>", css + "</head>", 1)


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.uploaders.coupang_uploader import CoupangUploader
    os.makedirs(OUT, exist_ok=True)
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title="수행방패 케이스", price="24000",
                   currency="KRW", source="extension", seller_id="u-shot",
                   extra={"options": [{"name": "색상", "values": COLORS}, {"name": "옵션", "values": ["기본"]}],
                          "images": ["https://img.alicdn.com/a.jpg"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    with patch.object(CoupangUploader, "_api_request", _api), \
            patch("src.seller_console.market_cred_view.resolve_upload_account", lambda: ""):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u-shot"
            html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
            prod = {"title": "수행방패 케이스", "price": 24000, "currency": "KRW", "sku": "617129397971",
                    "images": ["https://img.alicdn.com/a.jpg"],
                    "options": [{"name": "색상", "values": COLORS}, {"name": "옵션", "values": ["기본"]}]}
            r1 = c.post("/seller/collect/coupang/options", json={"product": prod})
            held = r1.get_json() if r1.status_code in (200, 422) and r1.is_json else None
            filled = {**prod, "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
                      "coupang_option_pick": {"색상": "黑色"}}
            r2 = c.post("/seller/collect/coupang/options", json={"product": filled})
            ok = r2.get_json() if r2.status_code in (200, 422) and r2.is_json else None
    print(f"[{TAG}] route:", "있음" if held else f"없음(HTTP {r1.status_code})")
    if held:
        print(f"[{TAG}] held holds:", held.get("holds"))
        print(f"[{TAG}] filled holds:", ok.get("holds"))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        open(f"/tmp/_f48c_{TAG}.html", "w").write(_inline(html))
        for name, data, typed in (("1-held", held, None), ("2-filled", ok, True)):
            pg = br.new_page(viewport={"width": 760, "height": 1200})
            pg.goto(f"file:///tmp/_f48c_{TAG}.html")
            pg.wait_for_timeout(300)
            pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
            if data:
                pg.evaluate("""([d, typed]) => {
                  if (typed) { _CP.attrs['적용모델'] = 'iPhone 15'; _CP.pick['색상'] = '黑色'; }
                  kgpRenderCoupangOptions(d);
                }""", [data, typed])
                pg.wait_for_timeout(200)
                pg.locator('[data-role="coupang-options"]').screenshot(path=f"{OUT}/f48c-{name}-{TAG}.png")
            else:
                pg.locator('[data-etab="options"].kgp-esec').first.screenshot(path=f"{OUT}/f48c-{name}-{TAG}.png")
            pg.close()
        br.close()
    print(f"[{TAG}] saved")


if __name__ == "__main__":
    main()
