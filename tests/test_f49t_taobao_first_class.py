"""F49-T 1단계 — 타오바오·티몰: 실측 도구 · 확장으로 열기 · 초안이 실제로 채워진다.

오너 브리프(2026-09-25):
  - 「원인 추측 금지 — 확장에서 실제 열었을 때 나오는 상태코드/리다이렉트/콘솔 오류 원문부터」
  - 「수집 로그 화면(보강 완료 4/5 필드)에 필드별 O/X와 실패 이유(셀렉터 없음/로그인 필요/lazy 미로딩)를
    원문으로. 4/5의 빠진 1개가 뭔지부터 화면이 말하게」
  - 「타오바오/티몰 URL 붙여넣으면 "서버가 못 여는 사이트 — 확장으로 열기" 버튼 즉시, 새 탭에서 열고
    확장이 끝내면 목록 자동 갱신. 서버 fetch 시도는 하지 않는다」

이 파일이 못박는 것:
  ① 페이지 진단(`kgpPageDiag`) — **실브라우저**에서 티몰 주소로 연 페이지의 HTTP·리다이렉트·벽·lazy·셀렉터
  ② 필드별 사유는 **잰 값에서만**(없으면 「사유 미상」)
  ③ ★ 붙여넣기 초안이 **실제로 채워진다** — 전엔 확장이 같은 상품을 담아도 「이미 수집한 상품」으로 끝나
     초안이 비어 있었고, 티몰은 키가 달라 **새 행**이 생겼다
  ④ 수집 화면 「확장으로 열기」 — 서버 fetch 0회 · 상태 들여다보기 라우트
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
TMALL = "https://detail.tmall.com/item.htm?id=617129397971"


# ---------------------------------------------------------------------------
# ① 페이지 진단 — 실브라우저
# ---------------------------------------------------------------------------

def _diag_js() -> str:
    """content_script에서 **진단 부분만** 잘라 온다(크롬 API 없이 페이지에서 돌 수 있는 부분)."""
    src = (EXT / "content_script.js").read_text(encoding="utf-8")
    a = src.index("function _kgpDetectWall()")
    b = src.index("\n}\n", a) + 3
    c = src.index("const _KGP_PAGE_ERRORS = [];")
    d = src.index("function extractProductMeta()", c)
    return src[a:b] + "\n" + src[c:d]


def _chrome():
    import glob
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


PAGE_OK = """<html><head><title>随行盾 天猫</title></head><body>
<h1 class="ItemTitle--mainTitle">SPORTLINK 随行盾</h1>
<div class="PicGallery--x"><img src="https://img.alicdn.com/a.jpg"></div>
<div id="description"><img data-ks-lazyload="https://img.alicdn.com/d1.jpg" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></div>
</body></html>"""

PAGE_WALL = """<html><head><title>淘宝网 - 请登录</title></head><body>
<div id="login"><div id="nc_1_wrapper">滑动验证</div></div></body></html>"""


@pytest.mark.parametrize("page,expect_wall", [(PAGE_OK, False), (PAGE_WALL, True)])
def test_page_diag_in_a_real_browser_on_a_tmall_address(page, expect_wall):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**_chrome())
        pg = br.new_page()
        pg.route("https://detail.tmall.com/**",
                 lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=page))
        pg.goto(TMALL)
        pg.add_script_tag(content=_diag_js())
        d = pg.evaluate("() => kgpPageDiag()")
        br.close()
    assert d["url"] == TMALL
    assert d["nav"]["redirects"] == 0 and d["nav"]["requested"] == TMALL
    # responseStatus는 브라우저가 줄 때만 숫자다 — 주면 200, 안 주면 null(지어내지 않는다)
    assert d["nav"]["status"] in (200, None)
    assert bool(d["wall"]) is expect_wall
    if not expect_wall:
        assert d["sel"]["title"] >= 1 and d["sel"]["gallery"] >= 1 and d["sel"]["detail"] == 1
        assert d["sel"]["options"] == 0                 # 이 페이지엔 SKU 자리가 없다 — 그대로 0
        assert d["lazy"] == {"total": 1, "pending": 1}   # data-ks-lazyload + 자리표시 gif


def test_diag_selectors_are_the_repos_own_taobao_branch_not_new_guesses():
    """셀렉터는 이 레포에 **이미 있던 것**만 — 갤러리·상세·옵션 = `_kgpSitePdp` 타오바오 갈래,
    제목 = `kgp-extractor.js` `_adapterTitle` 타오바오 줄. 새로 지어낸 자리 0."""
    src = (EXT / "content_script.js").read_text(encoding="utf-8")
    i = src.index("function _kgpSitePdp()")
    legacy = src[i:src.index("\n}\n", i)]
    ext = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
    title_line = next(l for l in ext.splitlines() if "(taobao|tmall)" in l and "sels:" in l)
    block = src[src.index("const _KGP_TB_SELECTORS"):src.index("function kgpPageDiag()")]
    groups = dict(re.findall(r'(\w+): "([^"]+)"', block))
    assert set(groups) == {"gallery", "detail", "options", "title"}
    for g in ("gallery", "detail", "options"):
        for sel in [x.strip() for x in groups[g].split(",")]:
            assert sel in legacy, (g, sel)
    norm = lambda x: x.replace('"', "'").replace(" i]", "]")
    for sel in [x.strip() for x in groups["title"].split(",")]:
        assert norm(sel) in norm(title_line), sel


# ---------------------------------------------------------------------------
# ② 필드별 사유 — 잰 값에서만
# ---------------------------------------------------------------------------

def test_field_reasons_come_only_from_the_measured_diag():
    from src.collectors.collect_status import clean_page_diag, compute_collect_status
    base = {"title": "x", "price": "10", "images": ["a"]}           # 상세·리뷰가 빈 상품

    def _reason(extra, key):
        return next(f for f in compute_collect_status(extra)["fields"] if f["key"] == key)["reason"]

    assert _reason(dict(base), "detail").startswith("사유 미상") and "진단이 없습니다" in _reason(dict(base), "detail")
    assert _reason({**base, "page_diag": clean_page_diag({"wall": "로그인·검증 요소 발견"})},
                   "detail") == "로그인 필요 — 로그인·검증 요소 발견"
    assert _reason({**base, "page_diag": clean_page_diag({"lazy": {"total": 4, "pending": 3}})},
                   "detail").startswith("lazy 미로딩 — 아직 안 불러온 이미지 3장")
    assert _reason({**base, "page_diag": clean_page_diag({"sel": {"detail": 0}})},
                   "detail").startswith("셀렉터 없음")
    assert _reason({**base, "page_diag": clean_page_diag({"sel": {"detail": 4}})},
                   "detail").startswith("자리는 있음(detail 4개)")
    assert _reason(dict(base), "price") == ""                       # 있는 필드엔 사유가 없다


def test_options_are_not_confirmed_none_when_the_page_had_an_sku_area():
    """★ 옵션이 비었고 가격·이미지가 있으면 「단일 상품 확인」(분모 제외)이었다 — 그런데 페이지에
    **옵션 자리가 있었다**고 쟀으면 그건 확인이 아니라 **못 읽은 것**이다."""
    from src.collectors.collect_status import clean_page_diag, compute_collect_status
    base = {"title": "x", "price": "10", "images": ["a"]}
    none_ok = next(f for f in compute_collect_status(dict(base))["fields"] if f["key"] == "options")
    assert none_ok["na"] is True                                    # 진단 없으면 예전 그대로
    had = compute_collect_status({**base, "page_diag": clean_page_diag({"sel": {"options": 6}})})
    opt = next(f for f in had["fields"] if f["key"] == "options")
    assert opt["na"] is False and opt["ok"] is False and opt["reason"].startswith("자리는 있음(options 6개)")
    assert "옵션" in had["missing"]


def test_page_diag_is_cleaned_before_it_is_stored():
    from src.collectors.collect_status import clean_page_diag
    d = clean_page_diag({"wall": "x" * 999, "nav": {"status": "200", "redirects": "2"},
                         "sel": {"gallery": "3", "evil": "<script>"}, "errors": ["e"] * 20, "junk": 1})
    assert len(d["wall"]) == 120 and d["nav"]["status"] is None and d["nav"]["redirects"] == 2
    assert d["sel"] == {"gallery": 3} and len(d["errors"]) == 5 and "junk" not in d


def test_the_drawer_says_why_a_field_is_missing(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    extra = {"title": "随行盾", "price": "24", "currency": "CNY", "images": ["https://img/a.jpg"],
             "page_diag": {"url": TMALL, "wall": "", "nav": {"status": 200, "redirects": 1,
                                                              "requested": "https://item.taobao.com/item.htm?id=617129397971"},
                           "lazy": {"total": 2, "pending": 2}, "sel": {"options": 0}, "errors": []}}
    iid = S.append(url=TMALL, title="随行盾", price="24", currency="CNY", source="extension",
                   seller_id="u-f49-drawer", extra=extra)
    iid = iid[0] if isinstance(iid, tuple) else iid
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f49-drawer"
        html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert 'data-role="field-reason"' in html and "lazy 미로딩 — 아직 안 불러온 이미지 2장" in html
    assert 'data-role="page-diag"' in html and "HTTP 200" in html and "리다이렉트 1회" in html
    assert "item.taobao.com/item.htm?id=617129397971" in html      # 요청 → 도착 원문


# ---------------------------------------------------------------------------
# ③ ★ 붙여넣기 초안이 실제로 채워진다
# ---------------------------------------------------------------------------

def _draft(seller: str, url: str):
    from src.collectors.share_collect import collect_input
    r = collect_input(url, seller_id=seller, source="preview", translate=False)
    assert r.get("ok") and r.get("kind") == "share_draft", r
    return r["item_id"]


def _ext_post(monkeypatch, seller: str, url: str, **extra):
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    body = {"url": url, "title": "SPORTLINK 随行盾", "price": "24", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"], "translate": False, **extra}
    with app.test_client() as c:
        return c.post("/api/v1/collect/extension", json=body).get_json()


def test_collecting_the_same_taobao_item_fills_the_draft_instead_of_saying_duplicate(monkeypatch):
    seller = "u-f49-same"
    iid = _draft(seller, "https://item.taobao.com/item.htm?id=617129397971")
    d = _ext_post(monkeypatch, seller, "https://item.taobao.com/item.htm?id=617129397971")
    assert d["draft_pending"] is True and d["item_id"] == iid


def test_collecting_on_tmall_reaches_the_draft_saved_under_the_taobao_url(monkeypatch):
    """★ 전엔 키가 달라(`detail.tmall.com:item:` vs `taobao:item:`) **새 행**이 생기고 초안은 비었다."""
    from src.seller_console import collect_history_store as S
    seller = "u-f49-tmall"
    iid = _draft(seller, TMALL)
    before = len(S.list_items(seller_id=seller)) if hasattr(S, "list_items") else None
    d = _ext_post(monkeypatch, seller, TMALL + "&spm=a1z10")
    assert d["draft_pending"] is True and d["item_id"] == iid
    if before is not None:
        assert len(S.list_items(seller_id=seller)) == before            # 새 행 0


def test_an_ordinary_collected_row_is_still_a_plain_duplicate(monkeypatch):
    """초안이 아닌 일반 수집 행은 예전 그대로 「이미 수집한 상품」(덮어쓰기는 force만)."""
    seller = "u-f49-plain"
    first = _ext_post(monkeypatch, seller, "https://www.amazon.com/dp/B0TEST1234")
    assert first.get("ok")
    again = _ext_post(monkeypatch, seller, "https://www.amazon.com/dp/B0TEST1234")
    assert again.get("duplicate") is True and not again.get("draft_pending")


def test_a_filled_draft_is_no_longer_pending(monkeypatch):
    """draft_pending → /enrich(한 곳의 병합 규칙) → 이미지가 들어오면 done. 그 뒤엔 초안이 아니다."""
    import src.api.extension_api as ext
    from src.order_webhook import app
    seller = "u-f49-fill"
    iid = _draft(seller, TMALL)
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    with app.test_client() as c:
        r = c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/a.jpg"],
                                                    "price": "24", "currency": "CNY",
                                                    "page_diag": {"wall": "", "sel": {"detail": 0}}}).get_json()
        assert r["ok"] is True
        with c.session_transaction() as s:
            s["user_id"] = seller
        st = c.get(f"/seller/collect/{iid}/state").get_json()
    assert st["enrich_state"] == "done" and st["images"] == 1
    # 채울 때 실어 보낸 페이지 진단이 **저장돼** 사유가 된다(안 저장하면 「진단이 없습니다」로 남는다).
    detail = next(m for m in st["missing"] if m["label"] == "상세")
    assert detail["reason"].startswith("셀렉터 없음")
    again = _ext_post(monkeypatch, seller, TMALL)
    assert not again.get("draft_pending")


def test_the_extension_fills_the_draft_through_enrich(tmp_path):
    """background.js — `draft_pending`이 오면 `/enrich`로 보낸다(노드로 **실행**해서 잰다)."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    src = (EXT / "background.js").read_text(encoding="utf-8")
    a = src.index("function _kgpEnrichBody(")
    b = src.index("async function handleCollect(", a)
    harness = src[a:b] + """
const calls = [];
globalThis.fetch = async (url, opt) => { calls.push({url, body: JSON.parse(opt.body)});
  return { ok: true, json: async () => ({ ok: true, changed: {images: 1}, filled: 3, total: 5 }) }; };
(async () => {
  const out = await _kgpFillDraft({serverUrl: "https://s", token: "t"},
    {ok: true, duplicate: true, draft_pending: true, item_id: "IID"},
    {images: ["a"], gallery_images: ["a"], price: "24", page_diag: {wall: ""}});
  const walled = await _kgpFillDraft({serverUrl: "https://s", token: "t"},
    {ok: true, draft_pending: true, item_id: "IID"}, {page_diag: {wall: "로그인·검증 요소 발견"}});
  console.log(JSON.stringify({out, walled, calls}));
})();
"""
    f = tmp_path / "h.js"
    f.write_text(harness, encoding="utf-8")
    res = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True, check=True).stdout)
    assert res["out"]["ok"] is True and res["out"]["enriched"] is True and "3/5" in res["out"]["message"]
    assert len(res["calls"]) == 1 and res["calls"][0]["url"] == "https://s/api/v1/collect/enrich"
    assert res["calls"][0]["body"]["item_id"] == "IID" and res["calls"][0]["body"]["gallery"] == ["a"]
    assert res["walled"]["ok"] is False and "로그인" in res["walled"]["error"]   # 벽이면 안 보낸다


# ---------------------------------------------------------------------------
# ④ 수집 화면 — 확장으로 열기(서버 fetch 0회)
# ---------------------------------------------------------------------------

def test_pasting_a_tmall_url_gives_an_open_in_extension_link_and_fetches_nothing(monkeypatch):
    import requests
    from src.order_webhook import app
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("fetch")))
    monkeypatch.setattr(requests.Session, "get", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("fetch")))
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f49-page"
        one = c.post("/seller/collect/preview", json={"url": TMALL, "translate": False}).get_json()
        bulk = c.post("/seller/collect/bulk", json={"urls": TMALL + "\nhttps://item.taobao.com/item.htm?id=1234567"}).get_json()
    assert calls == []
    assert one["open_url"].startswith("https://item.taobao.com/item.htm?id=617129397971") and "kgpsrc=app" in one["open_url"]
    assert all(r["open_url"] and "kgpsrc=app" in r["open_url"] for r in bulk["results"])


def test_non_taobao_urls_get_no_open_in_extension_link():
    from src.seller_console.views import extension_open_url
    assert extension_open_url("https://www.amazon.com/dp/B0X") == ""
    assert extension_open_url("javascript:alert(1)") == ""
    assert extension_open_url(TMALL).endswith("&kgpsrc=app")


def test_the_state_route_reports_missing_fields_with_reasons():
    from src.order_webhook import app
    seller = "u-f49-state"
    iid = _draft(seller, TMALL)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = seller
        st = c.get(f"/seller/collect/{iid}/state").get_json()
        other = c.get("/seller/collect/nope-404/state")
    assert st["ok"] is True and st["enrich_state"] == "pending"
    assert st["missing"] and all("reason" in m for m in st["missing"])
    assert other.status_code == 404


# ---------------------------------------------------------------------------
# 같은 유형(캡처에서 발견) — 통화를 모르면 USD·KRW로 짐작하지 않는다
# ---------------------------------------------------------------------------

def test_saving_without_a_currency_invents_neither_krw_nor_a_krw_price(monkeypatch):
    """캡처에서 찾은 것 — 타오바오 초안(통화 미상)을 저장하면 화면은 USD를 붙여 보냈고,
    서버는 빈 통화를 KRW로 두고 가격을 그대로 `price_krw`에 넣었다(위안 24 → 「24원」)."""
    from src.order_webhook import app
    saved = []

    class _A:
        def upsert_item(self, item):
            saved.append(item)
            return True

    monkeypatch.setattr("src.seller_console.market_status_sheets.MarketStatusSheetsAdapter", lambda: _A())
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f49-save"
        r = c.post("/seller/collect/save", json={"title": "随行盾", "price": "24", "sku": "617129397971"})
        k = c.post("/seller/collect/save", json={"title": "x", "price": "24000", "currency": "KRW", "sku": "k1"})
    assert r.status_code == 400 and "통화를 모릅니다" in r.get_json()["error"]
    assert k.get_json()["ok"]
    assert len(saved) == 1                                                     # 모르는 통화는 저장 0
    assert saved[0].currency == "KRW" and saved[0].price_krw == 24000        # 원화면 예전 그대로


def test_the_collect_page_never_labels_an_unknown_currency_usd(monkeypatch):
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f49-usd"
        html = c.get("/seller/collect").get_data(as_text=True)
    js = html[html.index("function renderPreview("):]
    assert "|| 'USD'" not in js and "통화 미상" in js
