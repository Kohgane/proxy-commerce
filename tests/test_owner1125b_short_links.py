"""오너 11-25 15:56 실기기 「반려·보류가 나면 사유를 보고 등록이 되게 — 저대로 끝이냐」 — 계약.

① 짧은 링크를 서버가 푼다(아마존 `a.co`·`amzn.to` · 알리 `a.aliexpress.com`·`s.click.aliexpress.com` · 타오바오 `e.tb.cn` — 한 입구)
   · 수집 때 정본 주소로 저장(원래 주소는 `raw_url`) · 이미 저장된 행은 사전검증 자리에서 풀어 SKU를 만든다(유저에게 묻지 않음)
   · 못 풀면 그때만 「원본 주소 넣기」 — 문구는 사실대로(「짧은 링크라 상품번호를 못 읽었어요」) · 입력칸 예시는 그 소싱처에 맞게
② 보류 코드마다 그 카드 안에서 고치는 길 — 「이 마켓 빼기」만 있는 카드 0
④ 공유 시트 문구는 담긴 그대로(「주소만 담았어요」 + 다음 행동 하나) · 잘리지 않게 · 썸네일 없으면 소싱처 아이콘
⑤ 마켓 결과가 다 오면 「사전검증 끝 — 통과 n · 보류 m」
네트워크는 재지 않는다 — `requests.get`을 고정한다(CI는 네트워크가 열려 있다 · 지뢰).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

M5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
SWIFT = Path("mobile/ios/Share/ShareViewController.swift").read_text(encoding="utf-8")


class _Resp:
    def __init__(self, status, location="", body=""):
        self.status_code, self.headers, self.text = status, ({"Location": location} if location else {}), body

    def iter_content(self, n, decode_unicode=False):
        yield self.text.encode("utf-8")

    def close(self):
        pass


@pytest.fixture
def net(monkeypatch):
    """`requests.get`을 주소 → 응답 표로 고정한다. 부른 주소는 `calls`에 남는다."""
    monkeypatch.setenv("KGP_SHORT_LINK_RESOLVE", "1")
    from src.collectors import link_diag
    link_diag._RESOLVED.clear()
    table, calls = {}, []
    import requests

    def fake_get(url, **kw):
        calls.append(url)
        for k, v in table.items():
            if url.startswith(k):
                return v
        return _Resp(404)
    monkeypatch.setattr(requests, "get", fake_get)
    return table, calls


# ── ① 해석기 ──────────────────────────────────────────────────────────────────

def test_amazon_short_link_resolves_to_dp_without_reading_the_page(net):
    from src.collectors.link_diag import resolve_share_link
    table, calls = net
    table["https://a.co/d/00RG5ThB"] = _Resp(301, "https://www.amazon.com/Otacle-D1-Folding-Knife/dp/B0CXYZ1234?ref_=x&th=1")
    r = resolve_share_link("https://a.co/d/00RG5ThB")
    assert r["ok"] and r["market"] == "amazon" and r["item_id"] == "B0CXYZ1234"
    assert r["canonical_url"] == "https://www.amazon.com/dp/B0CXYZ1234"
    assert calls == ["https://a.co/d/00RG5ThB"]                    # 상품 페이지는 받지 않는다(봇 차단 · 필요 없음)


def test_aliexpress_short_link_follows_two_hops(net):
    from src.collectors.link_diag import resolve_share_link
    table, _ = net
    table["https://a.aliexpress.com/_mKqBfXy"] = _Resp(302, "https://s.click.aliexpress.com/e/_abc?bz=1")
    table["https://s.click.aliexpress.com/e/_abc"] = _Resp(302, "https://ko.aliexpress.com/item/1005006123456789.html?spm=a2g0o&gatewayAdapt=x")
    r = resolve_share_link("https://a.aliexpress.com/_mKqBfXy")
    assert r["ok"] and r["item_id"] == "1005006123456789"
    assert r["canonical_url"] == "https://www.aliexpress.com/item/1005006123456789.html"
    assert [h["host"] for h in r["hops"]] == ["a.aliexpress.com", "s.click.aliexpress.com"]


def test_resolver_never_follows_off_market_hosts(net):
    from src.collectors.link_diag import resolve_share_link
    table, calls = net
    table["https://amzn.to/3abc"] = _Resp(301, "https://evil.example.com/steal")
    r = resolve_share_link("https://amzn.to/3abc")
    assert not r["ok"] and r["reason"].startswith("off_host")
    assert "https://evil.example.com/steal" not in calls             # 열린 프록시 금지


def test_failed_resolve_reason_is_kept(net):
    from src.collectors.link_diag import resolve_share_link
    table, _ = net
    table["https://a.co/d/blocked"] = _Resp(403)
    r = resolve_share_link("https://a.co/d/blocked")
    assert not r["ok"] and r["reason"] == "http_403"


def test_taobao_short_link_goes_through_the_same_entry(monkeypatch):
    from src.collectors import link_diag
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url, timeout=6: {
        "ok": True, "item_id": "744111222333", "canonical_url": "https://item.taobao.com/item.htm?id=744111222333", "reason": "ok"})
    link_diag._RESOLVED.clear()
    r = link_diag.resolve_share_link("https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc")
    assert r["ok"] and r["market"] == "taobao" and r["item_id"] == "744111222333"


# ── ① 수집 때 정본 주소로 · 원래 주소는 raw_url ────────────────────────────────

def test_collect_stores_canonical_url_and_keeps_raw(net, monkeypatch):
    from src.api import extension_api as E
    from src.seller_console import collect_history_store as S
    table, _ = net
    table["https://a.co/d/00RG5ThB"] = _Resp(301, "https://www.amazon.com/dp/B0CXYZ1234?ref_=x")

    class _P:
        title, images, price, currency, price_original = "OKNIFE Otacle D1", ["https://img.example/a.jpg"], "39.99", "USD", ""
    seen = []
    monkeypatch.setattr(E, "_dispatcher_collect", lambda: (lambda u: seen.append(u) or _P()))
    monkeypatch.setattr(E, "_upsert_catalog", lambda *a, **k: None)
    r = E.collect_one_url("https://a.co/d/00RG5ThB", seller_id="default", source="share")
    assert r["ok"] and seen == ["https://www.amazon.com/dp/B0CXYZ1234"]
    row = S.get(r["item_id"], seller_id="default")
    assert row["url"] == "https://www.amazon.com/dp/B0CXYZ1234"
    assert json.loads(row["extra_json"])["raw_url"] == "https://a.co/d/00RG5ThB"
    from src.collectors.product_key import vendor_sku
    assert vendor_sku(row["url"]) == "B0CXYZ1234"                    # 쿠팡 SKU가 선다


# ── ① 이미 저장된 행 — 사전검증 자리에서 푼다 ───────────────────────────────

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as _app
    _app.config["TESTING"] = True
    return _app


def test_prevalidate_resolves_saved_short_link_without_asking(app, net):
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.seller_console import views as V
    table, _ = net
    table["https://a.co/d/00RG5ThB"] = _Resp(301, "https://www.amazon.com/dp/B0CXYZ1234")
    iid = S.append(source="share", url="https://a.co/d/00RG5ThB", title="OKNIFE Otacle D1", price="39.99", currency="USD",
                   image="", seller_id="default", extra={"title_ko": "오나이프 오타클 D1", "images": ["https://img.example/a.jpg"]})
    pd = {"title": "OKNIFE Otacle D1", "images": ["https://img.example/a.jpg"], "price": "39.99", "currency": "USD"}
    with app.test_request_context():
        out, _rc = V._pv_prepare({"item_id": iid, "markets": ["coupang:gogane", "coupang:woojoo"]}, pd)
    assert out["_sku_probe"]["ok"] is True
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert ex["source_url_resolved"] == "https://www.amazon.com/dp/B0CXYZ1234" and ex["raw_url"] == "https://a.co/d/00RG5ThB"
    for m in ("coupang:gogane", "coupang:woojoo"):
        assert not [h for h in UploadDispatcher.readiness_holds(out, m) if h["fix"] == "source_url"]


def test_unresolvable_short_link_hold_says_what_happened():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "t", "images": ["https://img.example/a.jpg"], "price": "39",
          "_sku_probe": {"ok": False, "chosen": "https://a.co/d/x", "short": True, "resolve_reason": "http_403", "market": "amazon"}}
    [h] = [x for x in UploadDispatcher.readiness_holds(pd, "coupang:gogane") if x["fix"] == "source_url"]
    assert h["line"].startswith("짧은 링크라 상품번호를 못 읽었어요") and "403" in h["line"]
    assert "주소가 없어" not in h["line"]


def test_source_url_example_follows_the_source():
    from src.seller_console.views import source_url_example as ex
    assert "amazon.com/dp/" in ex("https://a.co/d/00RG5ThB")
    assert "aliexpress.com/item/" in ex("https://a.aliexpress.com/_x")
    assert "item.taobao.com" in ex("https://e.tb.cn/h.x?tk=1")
    assert "taobao" not in ex("https://www.yoshidakaban.com/product/1.html")
    assert 'placeholder="https://item.taobao.com/item.htm?id=…"' not in M5
    assert "esc(SRC_EXAMPLE)" in M5 and 'placeholder="{{ m5.src_example }}"' in M5


# ── ② 보류 코드마다 고치는 길 — 「이 마켓 빼기」만 있는 카드 0 ─────────────────

# 전용 버튼이 이미 있는 코드(번역·대표 사진·원본 주소·선주문·전압·배송비 비율·카테고리·가격대 나누기)는 빼고, 나머지 전부.
_CODES_NEED_ACTION = [
    ("small_images", "사진이 작아요"), ("pc", "대표 이미지가 0장이에요"), ("pc", "판매가가 없어요"),
    ("trademark", "상표 위험"), ("risk", "위험(주의)"), ("risk_block", "위험(차단)"), ("risk_skip", "등록 안 함"),
    ("risk_wait", "이미지 검사 대기"), ("option_short", "옵션값 25자 초과"), ("price", "옵션가 범위"),
    ("detail_blank", "상세가 비었어요"), ("ship_dims", "치수 확인 필요"), ("naver_kc", "네이버 KC 인증"),
    ("naver_required", "네이버 필수 칸: 대표 이미지"), ("naver_required", "네이버 필수 칸: 원산지"),
    ("block", "유통기한 임박"), ("not_ready", "아직 준비 중"),
]


def _hold_fix_fn():
    i = M5.index("  function holdFixHtml(r, already) {")
    j = M5.index("\n  }\n", i) + 4
    return M5[i:j]


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
@pytest.mark.parametrize("code,msg", _CODES_NEED_ACTION)
def test_every_hold_code_has_a_way_forward(code, msg):
    js = ("var esc = function (s) { return String(s); };\n" + _hold_fix_fn() +
          f"\nprocess.stdout.write(holdFixHtml({{hold: true, market: 'coupang:gogane', fixes: [{json.dumps(code)}], message: {json.dumps(msg)}}}, ''));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert 'data-role="m5-hold-acts"' in r.stdout
    assert re.search(r'data-role="m5-hold-act"|data-role="m5-hold-wait"|판매수수료율이 정해지면', r.stdout), r.stdout


def test_hold_actions_are_wired():
    assert "if (r.hold) h += holdFixHtml(r, h);" in M5
    for act in ("photo", "refetch", "price", "risk", "edit-title", "edit-option", "edit-desc", "ship", "discard", "docs"):
        assert f"act === '{act}'" in M5, act
    assert "/recollect" in M5 and "/discard" in M5


# ── ④ 공유 시트 ─────────────────────────────────────────────────────────────

def test_share_sheet_words_tell_what_was_kept(app):
    from src.seller_console.views import share_sheet_words
    with app.test_request_context():
        bare = share_sheet_words({"item_id": "x1", "title": "알리 접이식 수납"},
                                 {"url": "https://www.aliexpress.com/item/1005006123456789.html", "price": "", "extra_json": json.dumps({"images": []})})
        assert bare["headline"] == "주소만 담았어요" and bare["next_label"] == "다시 가져오기"
        assert bare["next_path"] == "/seller/m/item/x1" and "aliexpress.com" in bare["source_icon"]
        full = share_sheet_words({"item_id": "x2", "title": "t"}, {"url": "u", "price": "9", "extra_json": json.dumps({"images": ["a"]})}, thumb="https://t")
        assert full["headline"] == "담았어요 ✓" and full["next_label"] == "" and full["source_icon"] == ""


def test_ios_share_sheet_uses_server_words_and_does_not_clip():
    assert "titleL.numberOfLines = 0" in SWIFT and "subL.numberOfLines = 0" in SWIFT
    assert 'sub = "수집 목록에 들어갔어요"' not in SWIFT
    for k in ('j["headline"]', 'j["sub"]', 'j["source_icon"]', 'j["next_label"]'):
        assert k in SWIFT
    assert "if good && next == nil { self.autoClose(1.1) }" in SWIFT


# ── ⑤ 사전검증 끝 ───────────────────────────────────────────────────────────

def test_prevalidate_line_ends_when_all_markets_are_in():
    assert "function pvBusy() { return pvState === 'running' && (!pvOrder.length || pvPending.length > 0); }" in M5
    assert "'사전검증 끝 — 통과 ' + n + ' · 보류 '" in M5
    assert "var line = pvBusy()" in M5


def test_ali_share_keeps_address_only_draft_when_page_is_blocked(net, monkeypatch):
    """서버가 알리 페이지를 못 읽어도(봇 차단) 링크를 폈으면 「주소만 담은」 초안 — 정본 주소·공유 글 제목·원래 주소(raw_url)."""
    from src.api import extension_api as E
    from src.collectors.share_collect import collect_input
    from src.seller_console import collect_history_store as S
    table, _ = net
    table["https://a.aliexpress.com/_c1125"] = _Resp(302, "https://ko.aliexpress.com/item/1005007123456789.html?spm=x")

    class _Empty:
        title, images, price, currency, price_original = "", [], "", "USD", ""
    monkeypatch.setattr(E, "_dispatcher_collect", lambda: (lambda u: _Empty()))
    r = collect_input("【AliExpress】 접이식 원목 수납 박스 대용량 https://a.aliexpress.com/_c1125", seller_id="default",
                      source="share", translate=False)
    assert r["ok"] and r["kind"] == "share_draft"
    row = S.get(r["item_id"], seller_id="default")
    assert row["url"] == "https://www.aliexpress.com/item/1005007123456789.html"
    assert row["title"] == "접이식 원목 수납 박스 대용량"
    assert json.loads(row["extra_json"])["raw_url"] == "https://a.aliexpress.com/_c1125"
    assert r["message"].startswith("주소만 담았어요") and "펴진 링크가 오지 않아" not in r["message"]
