"""F49-T 2부 — 티몰·타오바오 **SKU 실물**(ICE 컨텍스트) 추출 계약.

실물: 오너 진단 파일에서 뽑은 `tests/fixtures/tmall_1064346880857_ice.json`(세션 토큰 제거).
전역 `window.__ICE_APP_CONTEXT__` → `loaderData.home.data.res`. 키 이름은 전부 이 실물에서 왔다(발명 0).

| # | 계약 |
|---|---|
| 1 | 제목·이미지 5·옵션(商品规格 → 3값)·SKU 3개(propPath → 조합) |
| 2 | 가격 = `price.priceMoney`(分) → 175.50 · 186.70 · 175.50 (원가, 优惠前) |
| 3 | 참고가 = `subPrice.priceMoney`(平台加补后) → 143.50 · 152.70 · 없음 — 원가 계산 미사용 |
| 4 | 재고 200 · 200 · **0** — 0은 등록 제외(드로어에 사유) |
| 5 | ICE가 있으면 DOM(tier2) 옵션 잡음 그룹을 버린다 |
| 6 | `field_sources.sku = "ice_context"` · ICE 없는 티몰 페이지 = SKU 0 + 「SKU 컨텍스트 없음」 |
| 7 | 두 읽는 길: 인라인 `<script>` 텍스트(격리 월드) · live 전역(MAIN world) |
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIX = json.loads(Path("tests/fixtures/tmall_1064346880857_ice.json").read_text(encoding="utf-8"))
EXTRACTOR = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
URL = "https://detail.tmall.com/item.htm?id=1064346880857"
CTX = {"loaderData": {"home": {"data": {"res": FIX}}}}

# ICE가 없을 때 DOM(tier2)이 옵션으로 잡을 **잡음** — 오너 실측의 「已售/可开专票/送赠品」 류를 select 두 개로 흉내.
NOISE = """
<label for="g">送赠品</label><select id="g"><option>请选择</option><option>纸巾一包</option><option>挂钩两个</option></select>
<label for="h">可开专票</label><select id="h"><option>请选择</option><option>是</option><option>否</option></select>
"""


def _chrome():
    import glob
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


def _extract(body_html: str, *, live_global=None):
    pw = pytest.importorskip("playwright.sync_api")
    html = f"<html><head><title>{FIX['item']['title']}-tmall.com天猫</title></head><body>{body_html}</body></html>"
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**_chrome())
        pg = br.new_page()
        if live_global is not None:
            pg.add_init_script(f"window.__ICE_APP_CONTEXT__ = {json.dumps(live_global, ensure_ascii=False)};")
        pg.route("https://detail.tmall.com/**",
                 lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))
        pg.route("https://*.alicdn.com/**", lambda r: r.fulfill(status=204, body=""))
        pg.goto(URL)
        pg.add_script_tag(content=EXTRACTOR)
        out = pg.evaluate("() => window.kgpExtractProduct({pageType: 'single'})")
        br.close()
    return out


def _inline():
    return f"<script>window.__ICE_APP_CONTEXT__ = {json.dumps(CTX, ensure_ascii=False)};</script>"


def _assert_fixture(out):
    assert out["title"].startswith("卫生间厕纸盒")
    assert len(out["images"]) == 5
    assert out["options"] == [{"name": "商品规格", "values": [
        "双位纸巾架【卷纸丨湿厕纸丨抽纸】", "纸巾架-抽屉款【可收纳卫生巾】", "售后品质保障丨购买无忧"]}]
    sk = out["skus"]
    assert [s["sku_id"] for s in sk] == ["6109794445837", "6109794445838", "6109794445839"]
    assert [s["spec"] for s in sk] == [[v] for v in out["options"][0]["values"]]
    assert [s["price"] for s in sk] == ["175.50", "186.70", "175.50"]
    assert [s["reference_price"] for s in sk] == ["143.50", "152.70", ""]
    assert [s["stock"] for s in sk] == [200, 200, 0]
    assert sk[2]["stock_text"] == "无货(限购10件)"
    assert all(s["currency"] == "CNY" for s in sk)
    assert out["price"] == "175.50" and out["currency"] == "CNY"        # 대표가 = sku2info["0"](起)
    assert out["field_sources"]["sku"] == "ice_context"
    assert out["field_sources"]["price"] == "ice_context"


def test_inline_script_path_in_a_real_browser():
    _assert_fixture(_extract(_inline() + NOISE))


def test_live_global_path_in_a_real_browser():
    _assert_fixture(_extract(NOISE, live_global=CTX))


def test_dom_noise_option_groups_are_dropped_when_ice_exists():
    out = _extract(_inline() + NOISE)
    names = [o["name"] for o in out["options"]]
    assert names == ["商品规格"] and "送赠品" not in names and "可开专票" not in names


def test_without_ice_the_page_says_sku_context_missing():
    out = _extract("<h1>某商品</h1>" + NOISE)
    assert out["skus"] == [] and out["field_sources"]["sku"] == "none"
    assert any("SKU 컨텍스트 없음" in w for w in out["warnings"])


def test_fen_is_converted_without_float_error():
    """分 → 元 은 정수 연산 — 17550 → 175.50, 5 → 0.05, 비숫자 → 빈 문자열."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**_chrome())
        pg = br.new_page()
        pg.route("https://detail.tmall.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<p>x</p>"))
        pg.goto(URL)
        ctx = {"loaderData": {"home": {"data": {"res": {
            "item": {"title": "t"},
            "skuBase": {"props": [{"pid": "1", "name": "颜色", "values": [{"vid": "1", "name": "红"}, {"vid": "2", "name": "蓝"}]}],
                        "skus": [{"propPath": "1:1", "skuId": "a"}, {"propPath": "1:2", "skuId": "b"}, {"propPath": "9:9", "skuId": "c"}]},
            "skuCore": {"sku2info": {"a": {"price": {"priceMoney": "5"}}, "b": {"price": {"priceMoney": "x"}},
                                     "c": {"price": {"priceMoney": "100"}}}}}}}}}
        pg.add_script_tag(content=f"window.__ICE_APP_CONTEXT__ = {json.dumps(ctx)};")
        pg.add_script_tag(content=EXTRACTOR)
        out = pg.evaluate("() => window.kgpExtractProduct({pageType: 'single'})")
        br.close()
    assert [s["price"] for s in out["skus"]] == ["0.05", ""]
    assert [s["sku_id"] for s in out["skus"]] == ["a", "b"]              # 모르는 pid:vid(9:9)는 짝을 안 짓는다


# ---------------------------------------------------------------------------
# 서버 — SKU를 **저장**하고 드로어가 보여 준다(전엔 저장하지 않았다)
# ---------------------------------------------------------------------------

def test_the_server_keeps_skus_and_the_drawer_marks_zero_stock(monkeypatch):
    import src.api.extension_api as ext
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-f49t2-sku"
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    skus = [{"spec": ["A"], "sku_id": "1", "price": "175.50", "currency": "CNY", "reference_price": "143.50",
             "stock": 200, "stock_text": "有货"},
            {"spec": ["B"], "sku_id": "2", "price": "175.50", "currency": "CNY", "reference_price": "",
             "stock": 0, "stock_text": "无货(限购10件)"},
            {"spec": [], "sku_id": "bad"}]
    with app.test_client() as c:
        d = c.post("/api/v1/collect/extension", json={
            "url": URL, "title": FIX["item"]["title"], "price": "175.50", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"], "skus": skus, "translate": False,
            "field_sources": {"sku": "ice_context"}}).get_json()
        assert d.get("ok"), d
        iid = d["item_id"]
        with c.session_transaction() as s:
            s["user_id"] = seller
        html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert [k["sku_id"] for k in ex["skus"]] == ["1", "2"]                 # 조합 없는 줄은 버린다
    assert ex["skus"][1]["stock"] == 0
    assert 'data-role="sku-table"' in html and "티몰 상태(ICE)" in html
    assert "등록 제외 — 재고 없음" in html and "143.50" in html
