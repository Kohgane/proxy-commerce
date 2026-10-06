"""Z5 후속(오너 2026-10-06) — 검수 카드(M5)·데스크톱 마켓 선택: 연결된 마켓 전부·전부 토글, 묶음 강제 없음.

기본 체크 = 지난 등록 → 설정(/seller/settings 「기본 등록 마켓」) → 우주대행 묶음(쿠팡 우주대행 + 고코스모스).
가족 유저 = 관리자 + `FAMILY_EMAILS` (공개 가입자는 공유 마켓 계정을 못 쓴다 — 화면·서버 둘 다).
"""
from __future__ import annotations

import re

import pytest

SIX = ["coupang:gogane", "smartstore:chezgoga", "coupang:woojoo", "smartstore:gocosmos", "shopify", "woocommerce"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.seller_console import market_cred_view as MCV, smartstore_routing as SR, market_credentials as mc
    st.reset_for_tests()
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com, Bro@Example.com")
    monkeypatch.delenv("MARKET_DEFAULT_BUSINESS", raising=False)
    monkeypatch.setattr(MCV, "coupang_account_choices", lambda: [
        {"code": "coupang:gogane", "account": "gogane", "label": "쿠팡 — 고가네", "ready": True, "missing": []},
        {"code": "coupang:woojoo", "account": "woojoo", "label": "쿠팡 — 우주대행", "ready": True, "missing": []}])
    monkeypatch.setattr(SR, "store_choices", lambda p=None: [
        {"code": "smartstore:chezgoga", "store": "chezgoga", "label": "스마트스토어 — 셰고가", "business": "gogane",
         "ready": True, "approved": True, "assigned": False, "note": "", "limit_text": "셰고가 850/1,000"},
        {"code": "smartstore:gocosmos", "store": "gocosmos", "label": "스마트스토어 — 고코스모스", "business": "woojoo",
         "ready": True, "approved": True, "assigned": True, "note": "", "limit_text": "고코스모스 881/1,000"}])
    monkeypatch.setattr(mc, "connected_markets", lambda sid, ms: {m: m in ("shopify", "woocommerce", "coupang", "smartstore")
                                                                  for m in ms})


def _client(email, seller="fam-z5b"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["email"] = seller, email
    return c


def _item(seller="fam-z5b"):
    from src.seller_console import collect_history_store as S
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=77001", seller_id=seller,
                    title="미니 무드등", price="69", currency="CNY",
                    extra={"title_ko": "미니 무드등", "images": ["https://img.alicdn.com/a.jpg"] * 2, "price": "69", "currency": "CNY"})


def _boxes(h):
    """M5 체크박스 — [(code, checked, disabled)]."""
    out = []
    for tag in re.findall(r'<input type="checkbox" name="m5-market"[^>]*>', h):
        code = re.search(r'value="([^"]+)"', tag).group(1)
        out.append((code, " checked" in tag, "disabled" in tag))
    return out


def test_no_setting_family_sees_all_six_and_woojoo_bundle_checked():
    c = _client("mom@example.com")
    h = c.get(f"/seller/m/item/{_item()}").get_data(as_text=True)
    b = _boxes(h)
    assert [x[0] for x in b] == SIX                                       # 11번가(미연결)는 안 보임
    assert not any(x[2] for x in b)                                       # 전부 토글(disabled 0)
    assert [x[0] for x in b if x[1]] == ["coupang:woojoo", "smartstore:gocosmos"]
    assert 'data-role="m5-pick-source"' in h and "우주대행 묶음(설정 없음)" in h


def test_family_is_case_insensitive_and_stranger_sees_one_line():
    h = _client("bro@example.com").get(f"/seller/m/item/{_item()}").get_data(as_text=True)
    assert [x[0] for x in _boxes(h)] == SIX
    h = _client("stranger@example.com", "stranger-z5b").get(f"/seller/m/item/{_item('stranger-z5b')}").get_data(as_text=True)
    codes = [x[0] for x in _boxes(h)]
    assert "coupang:woojoo" not in codes and codes[0] == "coupang"         # 공개 가입자: 예전처럼 한 줄씩
    assert [x[0] for x in _boxes(h) if x[1]] == ["coupang"]


def test_setting_then_last_pick(monkeypatch):
    import src.seller_console.views as V
    c = _client("mom@example.com")
    r = c.post("/seller/settings", data={"codes": ["coupang:gogane", "shopify", "bogus:x"]})
    assert r.status_code == 200 and "저장했어요" in r.get_data(as_text=True)
    h = c.get(f"/seller/m/item/{_item()}").get_data(as_text=True)
    assert [x[0] for x in _boxes(h) if x[1]] == ["coupang:gogane", "shopify"] and "설정의 기본 등록 마켓" in h
    page = c.get("/seller/settings").get_data(as_text=True)
    assert 'value="coupang:gogane" checked' in page and 'value="bogus:x"' not in page

    # 등록하면 그 선택을 기억 → 다음 카드의 처음 체크(설정보다 앞)
    class _Res:
        def to_dict(self):
            return {"results": []}

    class _D:
        def dispatch(self, pd, markets):
            return _Res()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    r = c.post("/seller/collect/upload", json={"product": {"title": "x", "price": "1000", "images": ["https://img.alicdn.com/a.jpg"]},
                                               "markets": ["smartstore:chezgoga", "woocommerce"]})
    assert r.status_code == 200, r.get_json()
    h = c.get(f"/seller/m/item/{_item()}").get_data(as_text=True)
    assert [x[0] for x in _boxes(h) if x[1]] == ["smartstore:chezgoga", "woocommerce"] and "지난번 등록에서 고른 마켓" in h
    # 같은 계정의 다른 가족도 같은 기억(계정 단위 — Stage 6 전까지 사용자별 아님)
    h2 = _client("bro@example.com", "bro-z5b").get(f"/seller/m/item/{_item('bro-z5b')}").get_data(as_text=True)
    assert [x[0] for x in _boxes(h2) if x[1]] == ["smartstore:chezgoga", "woocommerce"]
    # 설정을 다시 저장하면 기억은 지우고 설정이 처음 체크
    c.post("/seller/settings", data={"codes": ["coupang:woojoo"]})
    h = c.get(f"/seller/m/item/{_item()}").get_data(as_text=True)
    assert [x[0] for x in _boxes(h) if x[1]] == ["coupang:woojoo"]


def test_stranger_cannot_post_shared_account_codes(monkeypatch):
    c = _client("stranger@example.com", "stranger-z5b")
    for path in ("/seller/collect/upload", "/seller/collect/prevalidate"):
        r = c.post(path, json={"product": {"title": "x", "price": "1"}, "markets": ["coupang:woojoo"]})
        assert r.status_code == 403 and "공유 마켓" in r.get_json()["error"]


def test_desktop_review_same_rows_and_checks():
    c = _client("mom@example.com")
    h = c.get(f"/seller/collect/preview/{_item()}").get_data(as_text=True)
    tags = re.findall(r'<input class="form-check-input market-upload-check m-0" type="checkbox"[^>]*>', h)
    codes = [re.search(r'value="([^"]+)"', t).group(1) for t in tags]
    assert sorted(codes) == sorted(SIX) and not any("disabled" in t for t in tags)
    assert sorted(re.search(r'value="([^"]+)"', t).group(1) for t in tags if " checked" in t) == ["coupang:woojoo", "smartstore:gocosmos"]
    assert 'data-role="market-pick-source"' in h

