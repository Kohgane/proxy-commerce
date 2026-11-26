"""오너 11-26 감독 2 — 알리 공유 초안 카드에 **등록까지 가는 길**. 계약.

서버는 알리 상품 페이지를 못 읽는다(실측: 스크립트만 있는 빈 껍데기). 그래서 카드가 두 길을 말한다:
① 「PC 확장으로 채우기」(주소 복사 · PC 크롬 고가수집기) ② 폰에서 사진 직접 올리기 · 원가(통화 포함) · 옵션.
원가를 넣으면 등록 게이트가 열린다(가짜 값 0 — 셀러가 적은 값만, 「직접 수정」으로 표시).
"""
from __future__ import annotations

import json

import pytest

_MADE: list = []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from src.seller_console import collect_history_store as S
    for iid in _MADE:
        try:
            S.delete([iid], seller_id="default")
        except Exception:
            pass
    _MADE.clear()


def _ali_draft(**extra):
    from src.seller_console import collect_history_store as S
    ex = {"title": "", "title_ko": "", "images": [], "price": "", "currency": "", "mode": "share",
          "uncollected": ["price", "images", "options", "description"], "gate_ready": False, "enrich_state": "pending",
          "raw_url": "https://a.aliexpress.com/_mKbQx1Z"}
    ex.update(extra)
    iid = S.append(source="share", url="https://www.aliexpress.com/item/1005006412345678.html", title="(제목 없음)",
                   price="", currency="", image="", seller_id="default", extra=ex)
    _MADE.append(iid)
    return iid


def _extra(iid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_id="default")["extra_json"])


def test_card_shows_two_paths_for_ali_draft(client):
    iid = _ali_draft()
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-pc-fill"' in h and "PC 확장으로 채우기" in h
    assert 'value="https://www.aliexpress.com/item/1005006412345678.html"' in h and 'data-role="m5-pc-fill-copy"' in h
    # 폰 길 — 숨기지 않는다 · 알리 사진 안내(타오바오 중국어 안내가 아니라)
    assert 'data-role="m5-manual" data-item="' + iid + '" >' in h or ('data-role="m5-manual" data-item="' + iid + '" hidden') not in h
    assert "알리 앱에서 사진을 길게 눌러" in h and "保存图片" not in h
    assert 'data-role="m5-opt-cur"' in h and '<option value="KRW">KRW</option>' in h      # 통화가 비었으니 고르게
    assert "원가·옵션 저장" in h
    assert "아래 「폰에서 사진·원가 넣기」에 원가를 적거나" in h                              # 막힘 문장이 폰 길도 말한다


def test_price_only_save_opens_gate_and_card_unblocks(client):
    iid = _ali_draft(images=["https://ae01.alicdn.com/kf/S1.jpg"])
    d = client.post(f"/seller/collect/{iid}/manual-options", json={"options": [{"name": "", "values": ""}], "price": "23,900",
                                                                    "currency": "KRW"}).get_json()
    assert d["ok"] and d["price"] == "23900" and d["currency"] == "KRW" and d["sku_count"] == 0
    ex = _extra(iid)
    assert ex["price"] == "23900" and ex["currency"] == "KRW" and ex["gate_ready"] is True
    assert ex["price_source"] == "manual" and ex["field_sources"]["price"] == "manual" and "price" in ex["manual_fields"]
    assert "price" not in ex["uncollected"]
    from src.seller_console import views as V
    with client.application.test_request_context():
        from src.seller_console import collect_history_store as S
        ctx = V.mobile_list_ctx(S.get(iid, seller_id="default"))
    assert ctx["price"] == "23900" and not ctx["blocked"].startswith("가격이 없어")
    assert not ctx["pc_fill"]                                                  # 사진·가격이 다 찼으면 안내도 접는다


def test_price_without_currency_is_refused_honestly(client):
    iid = _ali_draft()
    r = client.post(f"/seller/collect/{iid}/manual-options", json={"options": [], "price": "23900"})
    assert r.status_code == 400 and "통화를 골라" in r.get_json()["error"]
    r2 = client.post(f"/seller/collect/{iid}/manual-options", json={"options": [], "price": "100", "currency": "BTC"})
    assert r2.status_code == 400
    assert _extra(iid).get("gate_ready") is False                              # 거부된 저장은 아무것도 열지 않는다


def test_options_with_price_and_currency_make_skus(client):
    iid = _ali_draft()
    d = client.post(f"/seller/collect/{iid}/manual-options", json={
        "options": [{"name": "색상", "values": "블랙, 화이트"}], "price": "15.5", "currency": "USD"}).get_json()
    assert d["ok"] and d["sku_count"] == 2 and d["currency"] == "USD"
    ex = _extra(iid)
    assert ex["gate_ready"] is True and {s["currency"] for s in ex["skus"]} == {"USD"}


def test_taobao_and_full_items_get_no_pc_fill(client):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=712345678901", title="(제목 없음)", price="", currency="CNY",
                   image="", seller_id="default", extra={"mode": "share", "images": [], "price": "", "currency": "CNY", "gate_ready": False})
    _MADE.append(iid)
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-pc-fill"' not in h and "保存图片" in h
    full = _ali_draft(images=["https://ae01.alicdn.com/kf/S1.jpg"], price="23900", currency="KRW", gate_ready=True)
    assert 'data-role="m5-pc-fill"' not in client.get(f"/seller/m/item/{full}").get_data(as_text=True)
