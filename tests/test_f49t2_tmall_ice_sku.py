"""F49-T 2부(-b) — 티몰·타오바오 **SKU 실물**(ICE 컨텍스트) 추출 계약.

## 2부-b (오너 실측 617129397971, ext 1.5.155, 2026-09-26 14:15Z)
페이지에 `__ICE_APP_CONTEXT__`·skuBase(颜色分类×10)·sku2info가 **전부 있는데** 확장 결과는 sku=none ·
skus 0 · price "" · 옵션은 DOM 잡음 4그룹(옵션17/색상13/12/11)이었다.
실페이지는 대입문이 아니라 **래퍼**다:

    !(function () {var a = window.__ICE_APP_CONTEXT__ || {};var b = {...JSON...};
      for (var k in a) {b[k] = a[k]}window.__ICE_APP_CONTEXT__=b;})();

옛 파서는 첫 `__ICE_APP_CONTEXT__`(= `|| {}` 쪽) 뒤 30자 안의 `=`만 봤고, 실패하면 그 스크립트를 통째로 건너뛰었다.
→ 그 스크립트의 `{`를 앞에서부터 중괄호 매칭 · 변수 이름 무관 · 파싱 실패 시 `ice_error`(앞 200자).
옛 픽스처(인라인 대입문)는 실페이지와 모양이 달라 **삭제**했다 — 두 실물 모두 래퍼 모양으로:

- `tests/fixtures/realpages/tmall_617129397971_ice_min.html` — 오너 최소 픽스처(수행방패, 颜色分类×10)
- `tests/fixtures/realpages/tmall_1064346880857_ice_min.html` — 오너 실물 JSON(1부)을 **같은 래퍼로** 감쌈
- `fixtures/realpages/diag/kgp-snapshot-detail-tmall-com-item-htm-id-617129397971.html` — 오너 업로드 실페이지(419KB)

| # | 계약 |
|---|---|
| 1 | 래퍼 모양에서 SKU·옵션·가격이 나온다(격리 월드 = 스크립트 텍스트 경로, 전역은 지운 상태로 잰다) |
| 2 | 수행방패 10 SKU · 재고 8/50/18/18/18/13/16/19/20/20 · 가격 29.90/34.90 · 대표가 29.90(sku2info["0"]) |
| 3 | ICE 성공이면 DOM 잡음 옵션 그룹 0(可开发票·加入购物车·中国段物流…) · field_sources.sku = ice_context |
| 4 | sku2info["0"]이 없으면 priceVO(최상위 · componentsVO 안 둘 다) |
| 5 | 파싱 실패 → `ice_error`(사유 + 앞 200자) + 경고 — 조용한 0건 금지 |
| 6 | live 전역 경로(MAIN world·북마클릿)는 그대로 |
| 7 | 병합(content script)이 ICE 옵션·SKU를 DOM 쪽 긴 목록으로 덮지 않는다 |
| 8 | 서버가 SKU를 저장하고 드로어 SKU 표에 10행 |
"""
from __future__ import annotations

import json
import re
import subprocess
import shutil
from pathlib import Path

import pytest

EXTRACTOR = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
URL = "https://detail.tmall.com/item.htm?id=617129397971"
F_617 = Path("tests/fixtures/realpages/tmall_617129397971_ice_min.html")
F_106 = Path("tests/fixtures/realpages/tmall_1064346880857_ice_min.html")
REAL = Path("fixtures/realpages/diag/kgp-snapshot-detail-tmall-com-item-htm-id-617129397971.html")

# 오너가 적은 순서(sku2info 키 순서)로 본 재고 — 집합으로 대조한다.
STOCK_617 = sorted([13, 19, 20, 8, 18, 18, 16, 50, 18, 20])
JUNK = ("可开发票", "加入购物车", "中国段物流", "已售", "送赠品", "可开专票")


def res_of(path) -> dict:
    """픽스처 HTML의 래퍼 JSON을 **파이썬 쪽에서 독립적으로** 읽는다(JS 파서와 같은 구현 금지 — 대조용)."""
    t = Path(path).read_text(encoding="utf-8")
    i = t.index("var b = {") + len("var b = ")
    depth, in_str, esc = 0, False, False
    for j in range(i, len(t)):
        c = t[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[i:j + 1])["loaderData"]["home"]["data"]["res"]
    raise AssertionError("래퍼 JSON이 닫히지 않음")


def _chrome():
    import glob
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


# 확장 격리 월드는 페이지 전역을 못 본다 — 실경로(스크립트 텍스트)를 재려고 전역을 지우고 추출한다.
_DROP_GLOBAL = "() => { try { delete window.__ICE_APP_CONTEXT__; } catch (e) {} window.__ICE_APP_CONTEXT__ = undefined; }"


def _extract(html: str, *, url=URL, drop_global=True, live_global=None):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**_chrome())
        pg = br.new_page()
        if live_global is not None:
            pg.add_init_script(f"window.__ICE_APP_CONTEXT__ = {json.dumps(live_global, ensure_ascii=False)};")
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                 if r.request.resource_type == "document" else r.abort())
        pg.goto(url, wait_until="domcontentloaded")
        if drop_global:
            pg.evaluate(_DROP_GLOBAL)
        pg.add_script_tag(content=EXTRACTOR)
        out = pg.evaluate("() => window.kgpExtractProduct({pageType: 'single'})")
        br.close()
    return out


# ICE가 없을 때 DOM(tier2)이 옵션으로 잡는 **잡음** — 오너 실측 그룹을 select로 흉내.
NOISE = """
<label for="g">可开发票</label><select id="g"><option>请选择</option><option>是</option><option>否</option></select>
<label for="h">加入购物车</label><select id="h"><option>请选择</option><option>立即购买</option><option>加入购物车</option></select>
"""


def _with_noise(path):
    return Path(path).read_text(encoding="utf-8").replace("<body>", "<body>" + NOISE, 1)


# ── 1·2·3 수행방패(오너 최소 픽스처) ────────────────────────────────────────────

def test_617_wrapper_gives_ten_skus_prices_and_stock():
    res = res_of(F_617)
    out = _extract(_with_noise(F_617))
    sk = out["skus"]
    assert len(sk) == 10, (len(sk), out.get("ice_error"), out.get("warnings"))
    names = [v["name"] for v in res["skuBase"]["props"][0]["values"]]
    assert out["options"] == [{"name": "颜色分类", "values": names}]
    assert sorted(s["stock"] for s in sk) == STOCK_617
    assert {s["price"] for s in sk} == {"29.90", "34.90"}
    assert all(s["currency"] == "CNY" for s in sk)
    by_id = {s["sku_id"]: s for s in sk}
    assert by_id["4852747022539"]["price"] == "34.90" and by_id["4852747022539"]["stock"] == 13
    assert by_id["4355552953967"]["spec"] == ["三合一充电支架（白色）"] and by_id["4355552953967"]["stock"] == 8
    assert out["price"] == "29.90" and out["currency"] == "CNY"          # sku2info["0"](优惠前 起)
    assert out["field_sources"]["sku"] == "ice_context" and out["field_sources"]["price"] == "ice_context"
    assert not out.get("ice_error")


def test_ice_success_drops_dom_junk_option_groups():
    out = _extract(_with_noise(F_617))
    flat = [v for o in out["options"] for v in [o["name"]] + list(o["values"])]
    assert not [j for j in JUNK if any(j in x for x in flat)], out["options"]


# ── 1부 실물(1064346880857)을 같은 래퍼로 ──────────────────────────────────────

def test_1064346880857_wrapper_still_gives_three_skus():
    out = _extract(_with_noise(F_106))
    sk = out["skus"]
    assert [s["sku_id"] for s in sk] == ["6109794445837", "6109794445838", "6109794445839"]
    assert [s["price"] for s in sk] == ["175.50", "186.70", "175.50"]
    assert [s["reference_price"] for s in sk] == ["143.50", "152.70", ""]
    assert [s["stock"] for s in sk] == [200, 200, 0]
    assert sk[2]["stock_text"] == "无货(限购10件)"
    assert out["options"][0]["name"] == "商品规格" and len(out["options"]) == 1
    assert out["price"] == "175.50"


# ── 오너 업로드 실페이지(419KB) ─────────────────────────────────────────────────

@pytest.mark.skipif(not REAL.exists(), reason=f"실페이지 스냅샷 없음: {REAL}")
def test_real_snapshot_617129397971():
    out = _extract(REAL.read_text(encoding="utf-8", errors="ignore"))
    assert len(out["skus"]) == 10, (out.get("ice_error"), out.get("warnings"))
    assert sorted(s["stock"] for s in out["skus"]) == STOCK_617
    assert out["price"] == "29.90"
    assert [o["name"] for o in out["options"]] == ["颜色分类"]
    flat = [v for o in out["options"] for v in o["values"]]
    assert not [j for j in JUNK if any(j in x for x in flat)]
    # 옛 결과의 이미지 14장 중 9장은 UI 아이콘(tps-48/56/96)이었다 — ICE 본 이미지 3장만.
    assert len(out["images"]) == 3 and not [u for u in out["images"] if "-tps-" in u]


# ── 4 priceVO 폴백 ────────────────────────────────────────────────────────────

def _wrap(ctx: dict, title="t") -> str:
    body = json.dumps(ctx, ensure_ascii=False)
    return (f"<html><head><title>{title}</title><script>!(function () {{var a = window.__ICE_APP_CONTEXT__ || {{}};"
            f"var b = {body};for (var k in a) {{b[k] = a[k]}}window.__ICE_APP_CONTEXT__=b;}})();</script></head>"
            f"<body><h1>{title}</h1></body></html>")


@pytest.mark.parametrize("where", ["top", "componentsVO"])
def test_price_falls_back_to_price_vo(where):
    res = json.loads(json.dumps(res_of(F_617)))
    res["skuCore"]["sku2info"].pop("0")
    pvo = res.pop("componentsVO")["priceVO"]
    if where == "top":
        res["priceVO"] = pvo
    else:
        res["componentsVO"] = {"priceVO": pvo}
    pvo["price"]["priceMoney"] = "2790"                      # sku 최저가(29.90)와 다른 값 — 출처가 갈린다
    out = _extract(_wrap({"loaderData": {"home": {"data": {"res": res}}}}))
    assert out["price"] == "27.90"


# ── 5 파싱 실패는 말한다 ───────────────────────────────────────────────────────

def test_parse_failure_is_reported_with_the_first_200_chars():
    broken = ('<html><head><title>x</title><script>!(function () {var a = window.__ICE_APP_CONTEXT__ || {};'
              'var b = {"loaderData":{"home":{"data":{"res":{"item":{"title":"x"},bad}}}}};'
              'window.__ICE_APP_CONTEXT__=b;})();</script></head><body></body></html>')
    out = _extract(broken)
    assert out["skus"] == [] and out["field_sources"]["sku"] == "none"
    err = out.get("ice_error") or ""
    assert err.startswith("JSON.parse 실패") and '{"loaderData"' in err and len(err) < 320, err
    assert any("파싱 실패" in w for w in out["warnings"])


def test_without_ice_the_page_says_sku_context_missing():
    out = _extract("<html><head><title>某商品</title></head><body><h1>某商品</h1>" + NOISE + "</body></html>")
    assert out["skus"] == [] and out["field_sources"]["sku"] == "none"
    assert any("SKU 컨텍스트 없음" in w for w in out["warnings"])
    assert not out.get("ice_error")


def test_fen_is_converted_without_float_error():
    ctx = {"loaderData": {"home": {"data": {"res": {
        "item": {"title": "t"},
        "skuBase": {"props": [{"pid": "1", "name": "颜色", "values": [{"vid": "1", "name": "红"}, {"vid": "2", "name": "蓝"}]}],
                    "skus": [{"propPath": "1:1", "skuId": "a"}, {"propPath": "1:2", "skuId": "b"}, {"propPath": "9:9", "skuId": "c"}]},
        "skuCore": {"sku2info": {"a": {"price": {"priceMoney": "5"}}, "b": {"price": {"priceMoney": "x"}},
                                 "c": {"price": {"priceMoney": "100"}}}}}}}}}
    out = _extract(_wrap(ctx))
    assert [s["price"] for s in out["skus"]] == ["0.05", ""]
    assert [s["sku_id"] for s in out["skus"]] == ["a", "b"]              # 모르는 pid:vid(9:9)는 짝을 안 짓는다


# ── 6 live 전역(MAIN world·북마클릿) ────────────────────────────────────────────

def test_live_global_path_still_works():
    ctx = {"loaderData": {"home": {"data": {"res": res_of(F_617)}}}}
    out = _extract("<html><head><title>x</title></head><body><h1>x</h1></body></html>",
                   drop_global=False, live_global=ctx)
    assert len(out["skus"]) == 10 and out["field_sources"]["sku"] == "ice_context"


# ── 7 병합이 ICE를 덮지 않는다 ─────────────────────────────────────────────────

def test_merge_keeps_ice_options_over_longer_dom_lists():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 미설치")
    a = CS.index("function kgpMergeMeta(")
    b = CS.index("\n}\n", a) + 3
    js = CS[a:b] + """
const base = {options: [{name: "颜色分类", values: ["白"]}], skus: [{spec: ["白"]}], field_sources: {sku: "ice_context"}};
const extra = {options: [{name: "옵션", values: ["可开发票"]}, {name: "색상", values: ["a"]}], skus: [{spec: ["x"]}, {spec: ["y"]}]};
const plain = {options: [{name: "o", values: ["1"]}], skus: [], field_sources: {sku: "none"}};
console.log(JSON.stringify({ice: kgpMergeMeta(base, extra), plain: kgpMergeMeta(plain, extra)}));
"""
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30).stdout)
    assert out["ice"]["options"] == [{"name": "颜色分类", "values": ["白"]}] and len(out["ice"]["skus"]) == 1
    assert len(out["plain"]["options"]) == 2                             # ICE 아니면 종전 규칙(긴 쪽) 그대로


# ── 8 서버 저장 · 드로어 10행 ───────────────────────────────────────────────────

def _skus_payload():
    res = res_of(F_617)
    names = {f"1627207:{v['vid']}": v["name"] for v in res["skuBase"]["props"][0]["values"]}
    info = res["skuCore"]["sku2info"]
    return [{"spec": [names[s["propPath"]]], "sku_id": s["skuId"],
             "price": f"{int(info[s['skuId']]['price']['priceMoney']) / 100:.2f}", "currency": "CNY",
             "reference_price": "", "stock": info[s["skuId"]]["quantity"],
             "stock_text": info[s["skuId"]]["quantityText"]} for s in res["skuBase"]["skus"]]


def test_the_server_keeps_skus_and_the_drawer_shows_ten_rows(monkeypatch):
    import src.api.extension_api as ext
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-f49t2b-sku"
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    skus = _skus_payload() + [{"spec": [], "sku_id": "bad"}]
    with app.test_client() as c:
        d = c.post("/api/v1/collect/extension", json={
            "url": URL, "title": res_of(F_617)["item"]["title"], "price": "29.90", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"], "skus": skus, "translate": False,
            "field_sources": {"sku": "ice_context"}}).get_json()
        assert d.get("ok"), d
        with c.session_transaction() as s:
            s["user_id"] = seller
        html = c.get(f"/seller/collect/preview/{d['item_id']}").get_data(as_text=True)
    ex = json.loads(S.get(d["item_id"], seller_ids={seller})["extra_json"])
    assert len(ex["skus"]) == 10                                         # 조합 없는 줄은 버린다
    table = html.split('data-role="sku-table"', 1)[1].split("</table>", 1)[0]
    rows = re.findall(r"<tr[^>]*>\s*<td", table)
    assert len(rows) == 10, len(rows)
    assert "三合一充电支架（白色）" in table and "34.90" in table and "티몰 상태(ICE)" in html
