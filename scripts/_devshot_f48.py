"""F48 캡처 — 같은 스크립트를 main 워크트리(before)와 작업 트리(after)에서 돌린다.

쿠팡 쪽은 relay_request만 목으로 바꾼다(메타·출고지·POST 거부 본문). 그 위의 체인
(CoupangUploader → 브리지 → UploadDispatcher → 화면 JS)은 **그 트리의 실코드**다.

사용: python _devshot_f48.py <before|after> <out_dir>
"""
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ["COUPANG_IMAGE_SCREEN"] = "0"
ENV = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000274592",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "22796911",
    "COUPANG_RETURN_ZIP_CODE": "06000", "COUPANG_RETURN_ADDRESS": "서울시 강남구 테헤란로 1",
    "COUPANG_RETURN_CHARGE_NAME": "반품담당", "COUPANG_COMPANY_CONTACT_NUMBER": "02-000-0000",
}
os.environ.update(ENV)
SCENE = os.environ.get("F48_SCENE", "hold")   # hold: 해외 칸 비움+색상 누락 / reject: 다 채우고 쿠팡이 거부
if SCENE == "reject":
    os.environ["COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE"] = "25099966"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")

# 볼트 「조용한 실패」의 실응답 한 벌 + 문서 응답 예시 모양의 errorItems.
REJECT = {"code": "ERROR",
          "message": "유효하지 않은 ISBN 값이 존재합니다.|유효하지 않은 구매 옵션 값이 존재합니다.",
          "errorItems": [{"itemAttributes": [{"message": "색상: 허용되지 않는 값입니다(黑色)"}]}]}
META = {"attributes": [
    {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER",
     "basicUnit": "개", "usableUnits": ["개"], "exposed": "EXPOSED", "groupNumber": "NONE"},
    {"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING",
     "exposed": "EXPOSED", "groupNumber": "NONE"}] if SCENE == "hold" else [
    {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER",
     "basicUnit": "개", "usableUnits": ["개"], "exposed": "EXPOSED", "groupNumber": "NONE"}],
    "noticeCategories": [], "requiredDocumentNames": []}
OUTBOUND = [
    {"outboundShippingPlaceCode": 25099966, "shippingPlaceName": "ForAmazon", "addressType": "OVERSEA",
     "placeAddresses": [{"returnAddress": "Sunnyvale CA"}]},
    {"outboundShippingPlaceCode": 22796911, "shippingPlaceName": "장말로 출고지", "addressType": "DOMESTIC",
     "placeAddresses": [{"returnAddress": "경기 김포시"}]},
]


class _R:
    def __init__(self, status, body):
        self.status_code = status
        self.text = json.dumps(body, ensure_ascii=False)
        self.content = self.text.encode()
        self.headers = {}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code), response=self)


def _relay(method, url, **kw):
    if "categorization/predict" in url:
        return _R(200, {"code": "SUCCESS", "data": {"predictedCategoryId": "63955"}})
    if "category-related-metas" in url:
        return _R(200, {"code": "SUCCESS", "data": META})
    if "shipping-place/outbound" in url:
        if "placeCodes=" in url:
            code = url.split("placeCodes=")[-1].split("&")[0]
            return _R(200, {"code": "SUCCESS", "data": [r for r in OUTBOUND
                                                          if str(r["outboundShippingPlaceCode"]) == code]})
        return _R(200, {"code": "SUCCESS", "data": {"content": OUTBOUND}})
    if "return-shipping-center" in url or "returnShippingCenters" in url:
        return _R(200, {"code": "SUCCESS", "data": {"content": [
            {"returnCenterCode": "1000274592", "shippingPlaceName": "반품지", "placeAddresses": []}]}})
    if "coupang-delivery-companies" in url:
        return _R(200, {"code": "SUCCESS", "data": [{"deliveryCompanyCode": "CJGLS",
                                                        "deliveryCompanyName": "CJ대한통운"}]})
    if method == "POST" and "seller-products" in url:
        return _R(400, REJECT)
    return _R(200, {"code": "SUCCESS", "data": []})


def _inline(html):
    css = ""
    if os.path.exists(BOOTSTRAP):
        css += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    css += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for e in EXTRA_CSS:
        if os.path.exists(e):
            css += "<style>" + open(e, encoding="utf-8").read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js", encoding="utf-8").read() + "</script>"
    html = html.replace('<script src="/seller/static/seller.js"></script>', js)
    return html.replace("</head>", css + "</head>", 1)


def main():
    from unittest.mock import patch
    import src.uploaders.coupang_uploader as CU
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import UploadDispatcher

    os.makedirs(OUT, exist_ok=True)
    product = {"title": "수행방패 휴대용 방패", "price": 24000, "currency": "KRW", "sku": "617129397971",
               "images": ["https://img.example/1.jpg"], "description": "상세", "origin": "중국",
               "source_url": "https://detail.tmall.com/item.htm?id=617129397971",
               "options": [{"name": "颜色分类", "values": ["黑色"]}]}
    item_id = S.append(url=product["source_url"], title=product["title"], price="24000",
                       currency="KRW", source="extension", seller_id="default",
                       extra={"images": product["images"], "options": product["options"]})
    if isinstance(item_id, tuple):
        item_id = item_id[0]

    import contextlib
    # 이미지 HEAD(사전검증의 다른 게이트)는 캡처 대상이 아니다 — 대역 이미지라 통과만 시킨다.
    with patch.object(CU, "relay_request", _relay), \
            patch("urllib.request.urlopen", lambda *a, **k: contextlib.nullcontext()), \
            patch("time.sleep", lambda s: None):
        disp = UploadDispatcher().dispatch(product, ["coupang"]).to_dict()
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "default"
            # 사전검증은 **화면이 부르는 라우트 그대로** — 라벨·직렬화까지 실경로.
            pre = c.post("/seller/collect/prevalidate",
                         json={"product": product, "markets": ["coupang"]}).get_json()["results"]
            lk = c.post("/seller/markets/connect/coupang/lookup", json={})
            lookup = lk.get_json()
            prev_html = c.get(f"/seller/collect/preview/{item_id}").get_data(as_text=True)
            conn_html = c.get("/seller/markets/connect/coupang").get_data(as_text=True)

    print(f"[{TAG}/{SCENE}] prevalidate:", json.dumps(pre, ensure_ascii=False)[:600])
    print(f"[{TAG}/{SCENE}] dispatch:", json.dumps(disp, ensure_ascii=False)[:600])
    print(f"[{TAG}/{SCENE}] lookup http={lk.status_code}:", json.dumps(lookup, ensure_ascii=False)[:500])

    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        # ① 사전검증 · ② 등록 결과 — 편집 화면의 실제 렌더 함수
        path = f"/tmp/_f48_prev_{TAG}.html"
        open(path, "w", encoding="utf-8").write(_inline(prev_html))
        pg = br.new_page(viewport={"width": 1100, "height": 900})
        pg.goto(f"file://{path}")
        pg.wait_for_timeout(500)
        pg.evaluate("""([pre, disp]) => {
          if (typeof kgpEtab === 'function') kgpEtab('upload');
          const m = document.getElementById('uploadModal') || document.querySelector('.modal');
          renderPrevalidateResults(pre);
          renderUploadResults({ok: true, result: disp});
          const box = document.createElement('div');
          box.id = 'f48shot';
          box.style.cssText = 'padding:24px;background:var(--paper,#fff);max-width:760px';
          box.innerHTML = '<h6 class="pc-overline">사전검증</h6>'
            + document.getElementById('prevalidateResults').innerHTML
            + '<h6 class="pc-overline mt-3">등록 결과</h6>'
            + document.getElementById('uploadResults').innerHTML;
          document.body.innerHTML = '';
          document.body.appendChild(box);
        }""", [pre, disp])
        pg.wait_for_timeout(200)
        pg.locator("#f48shot").screenshot(path=f"{OUT}/f48-{SCENE}-{TAG}.png")
        pg.close()

        if SCENE == "hold":
            path = f"/tmp/_f48_conn_{TAG}.html"
            open(path, "w", encoding="utf-8").write(_inline(conn_html))
            pg = br.new_page(viewport={"width": 1100, "height": 900})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(500)
            pg.evaluate("""(data) => {
              const form = document.querySelector('[data-action="coupang-lookup"]').closest('form');
              const out = form.querySelector('[data-role="coupang-lookup-out"]');
              out.innerHTML = renderLookup(form, data);
              out.classList.remove('d-none');
              const box = document.createElement('div');
              box.id = 'f48lk';
              box.style.cssText = 'padding:24px;background:var(--paper,#fff);max-width:760px';
              box.appendChild(out);
              document.body.innerHTML = '';
              document.body.appendChild(box);
            }""", lookup)
            pg.wait_for_timeout(200)
            pg.locator("#f48lk").screenshot(path=f"{OUT}/f48-lookup-{TAG}.png")
            pg.close()
        br.close()
    print("saved", OUT)


if __name__ == "__main__":
    main()
