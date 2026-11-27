"""오너 11-27 감독 2 — 탭 줄이기 계약.

ⓐ 카드가 열리면 기억된 마켓으로 사전검증을 저절로(읽기 · 전송 0) → 첫 버튼이 곧 「통과한 n곳만 등록」.
   덜 된 카드·막힌 카드·이미 올라간 마켓은 안 돈다 · `M5_AUTO_PREVALIDATE=0`이면 끈다.
ⓑ 설정 「기본 등록 마켓」을 한 번 정하면 첫 카드부터 그 마켓이 체크돼 있다(자기 키 셀러도).
쿠팡 조회: 같은 상품을 다시 열면 카테고리 예측·메타는 프로세스 캐시(6시간)에서 — 쿠팡 호출 0.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "connected_markets", lambda sid, markets: {m: True for m in markets})
    app.config["TESTING"] = True
    return app.test_client()


def _row(**ex):
    from src.seller_console import collect_history_store as S
    e = {"title_ko": "OKNIFE 오타클 접이식 포켓 나이프", "images": ["https://m.media-amazon.com/images/I/81a._AC_SL1500_.jpg"],
         "price": "36372", "currency": "KRW"}
    e.update(ex)
    return S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE", price="36372", currency="KRW",
                    image="", seller_id="default", extra=e)


def test_complete_card_auto_prevalidates_and_js_runs_it(client):
    h = client.get(f"/seller/m/item/{_row()}").get_data(as_text=True)
    assert 'data-autopv="1"' in h
    assert "root.getAttribute('data-autopv') === '1' && !blocked" in h and "resetGo(); runCheck(_am, false);" in h
    assert "마켓에 보내지 않아요" in h


def test_switch_off_does_not(client, monkeypatch):
    monkeypatch.setenv("M5_AUTO_PREVALIDATE", "0")
    assert 'data-autopv="0"' in client.get(f"/seller/m/item/{_row()}").get_data(as_text=True)


def test_already_registered_market_is_skipped():
    from src.seller_console.views import _m5_auto_pv
    ms = [{"code": "coupang", "checked": True, "connected": True, "registered": {"line": "이미 등록"}}]
    assert _m5_auto_pv(ms, "", []) is False
    assert _m5_auto_pv([{"code": "coupang", "checked": True, "connected": True}], "", []) is True
    assert _m5_auto_pv([{"code": "coupang", "checked": True, "connected": False}], "", []) is False
    assert _m5_auto_pv([{"code": "coupang", "checked": True, "connected": True}], "막힘", []) is False
    assert _m5_auto_pv([{"code": "coupang", "checked": True, "connected": True}], "", [{"code": "sku_filling"}]) is False   # 덜 된 카드


def test_default_market_setting_checks_first_card(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    from src.seller_console import market_pick as MP
    sc = MP.scope("seller42", shared=False)
    MP.save_default(sc, ["smartstore"])
    rows = [{"code": "coupang", "connected": True}, {"code": "smartstore", "connected": True}]
    pick = MP.apply_checks(rows, sc, shared=False)
    assert pick["source"] == "setting" and [r["code"] for r in rows if r["checked"]] == ["smartstore"]


def test_coupang_predict_and_meta_are_cached_across_uploaders(monkeypatch):
    from src.uploaders import coupang_uploader as CU
    calls = []

    def fake(self, method, path, data=None, **k):
        calls.append(path)
        if "predict" in path:
            return {"data": {"autoCategorizationPredictionResultType": "SUCCESS", "predictedCategoryId": "78293",
                             "predictedCategoryName": "접이식 칼"}}
        return {"data": {"attributes": [], "noticeCategories": []}}
    monkeypatch.setattr(CU.CoupangUploader, "_api_request", fake)
    for _ in range(3):                                                    # 카드를 세 번 열었다(업로더는 매번 새로)
        up = CU.CoupangUploader(account="gogane")
        assert up.predict("OKNIFE 오타클 접이식 포켓 나이프")["id"] == "78293"
        up.get_category_meta("78293")
    assert len([c for c in calls if "predict" in c]) == 1 and len([c for c in calls if "meta" in c]) == 1
    assert CU.shared_cache_stats()["hit"] >= 4


def test_overseas_outbound_found_automatically_when_exactly_one(monkeypatch):
    """오너 11-27 오후 ② OKNIFE: 「구매대행 출고지 (해외)」가 비어 보류 — 쿠팡 출고지 목록(읽기만)에 해외가 하나면 그걸 쓴다.
    여럿이면 고르라고 · 없으면 예전 안내 그대로 · 저장(설정 쓰기) 0."""
    from src.uploaders import coupang_uploader as CU
    monkeypatch.setenv("COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", "")
    monkeypatch.setenv("COUPANG_GOGANE_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", "")
    rows = {"one": [{"outboundShippingPlaceCode": 25099966, "addressType": "DOMESTIC", "usable": True},
                    {"outboundShippingPlaceCode": 31234567, "addressType": "OVERSEA", "usable": True},
                    {"outboundShippingPlaceCode": 39999999, "addressType": "OVERSEA", "usable": False}],
            "two": [{"outboundShippingPlaceCode": 31234567, "addressType": "OVERSEA"}, {"outboundShippingPlaceCode": 31234568, "addressType": "OVERSEA"}],
            "none": [{"outboundShippingPlaceCode": 25099966, "addressType": "DOMESTIC"}]}
    for case, want in (("one", ("31234567", "")), ("two", ("", "2곳")), ("none", ("", "비어 있습니다"))):
        CU._SHARED.clear()
        calls = []
        monkeypatch.setattr(CU.CoupangUploader, "_api_request",
                            lambda self, m, path, data=None, **k: (calls.append((m, path)), {"code": "SUCCESS", "data": {"content": rows[case]}})[1])
        up = CU.CoupangUploader(account="gogane", vendor_id="A01381223")
        up.delivery_method = "AGENT_BUY"
        code, why = up.outbound_for_delivery()
        assert code == want[0] and (want[1] in why if want[1] else why == ""), (case, code, why)
        assert all(m == "GET" for m, _p in calls)                                          # 읽기만
