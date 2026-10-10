"""Y7-L(오너 2026-10-10 19:55 KST) — 카드 「A/S 연락처 넣기 →」가 마켓 연동 화면으로 가는데 그 화면에 A/S 전화 칸이 없었다
(Client ID·Secret·Channel ID만). 값은 서버 환경변수 `NAVER_<STORE>_AS_PHONE` → `NAVER_AS_PHONE`뿐.

계약
- 연동 화면 스마트스토어 패널에 스토어별(셰고가·고코스모스) 「A/S 전화번호」 칸(`#naver-as`) — 저장은 셀러 설정(공유 사용자 한 벌).
- 읽기: 설정 > 서버 환경변수. 칸 저장만으로도, env만 있어도 사전검증 통과. 둘 다 없으면 보류 → 링크가 그 칸(#naver-as).
"""
from __future__ import annotations

import pytest

FAM = "fam-y7l@example.com"


@pytest.fixture
def naver(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_SECRET", "sec")
    for k in ("NAVER_AS_PHONE", "NAVER_CHEZGOGA_AS_PHONE", "NAVER_GOCOSMOS_AS_PHONE"):
        monkeypatch.delenv(k, raising=False)
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(NC, "name_of", lambda cid: "패션의류>여성의류>정장세트")
    from src.db import image_translate_queue_pg as st
    for k in [k for k in list(getattr(st, "_MEM_STATE", {})) if k.startswith("naver_as:")]:
        st._MEM_STATE.pop(k, None)
    return monkeypatch


def _pd():
    return {"title_ko": "플리츠 세트", "coupang_name": "플리츠 미니멀 여성 여름 세트", "sell_price_krw": 52000,
            "images": ["https://img.alicdn.com/a.jpg"], "description_html": "<p>본문</p>", "naver_category_id": "50000816",
            "item_id": "it-7l", "url": "https://detail.tmall.com/item.htm?id=1", "brand": ""}


def _as_codes(store=""):
    from src.seller_console.upload_dispatcher import naver_payload_holds, _for_market
    _b, ctx = _for_market(f"smartstore:{store}" if store else "smartstore")
    with ctx:
        return [h for h in naver_payload_holds(_pd(), "it-7l") if "afterService" in h["code"]]


def test_neither_setting_nor_env_holds_and_links_to_the_field(naver):
    holds = _as_codes()
    assert holds and holds[0]["action_url"] == "/seller/markets/connect/smartstore#naver-as"
    assert "「A/S 전화번호」 칸" in holds[0]["line"]


def test_field_saved_passes(naver):
    from src.uploaders import naver_as as NAS
    NAS.save({"default": "010-1234-5678"}, shared=False)
    assert _as_codes() == []


def test_env_only_passes(naver):
    naver.setenv("NAVER_AS_PHONE", "02-555-0000")
    assert _as_codes() == []


def test_setting_wins_over_env_per_store(naver):
    naver.setenv("NAVER_CHEZGOGA_AS_PHONE", "02-555-0000")
    from src.uploaders import naver_as as NAS
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    assert SS(account="chezgoga").as_phone() == "02-555-0000"                          # env 폴백
    NAS.save({"chezgoga": "010-9999-8888"}, shared=False)
    assert SS(account="chezgoga").as_phone() == "010-9999-8888"                        # 설정 > env
    assert SS(account="gocosmos").as_phone() == ""                                     # 스토어별 — 다른 스토어로 새지 않음
    body = SS(account="chezgoga")._build_product_payload({"title": "x", "price": 1000, "images": ["https://a/b.jpg"],
                                                          "category_id": "50000816"})
    assert body["originProduct"]["detailAttribute"]["afterServiceInfo"]["afterServiceTelephoneNumber"] == "010-9999-8888"
    NAS.save({"chezgoga": ""}, shared=False)                                           # 비우면 서버 기본값으로
    assert SS(account="chezgoga").as_phone() == "02-555-0000"


def test_connect_page_has_the_field_and_saves(naver):
    naver.setenv("FAMILY_EMAILS", FAM)
    naver.setenv("NAVER_GOCOSMOS_AS_PHONE", "02-777-0000")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7l", user_email=FAM, user_role="seller")
    html = c.get("/seller/markets/connect/smartstore").get_data(as_text=True)
    assert 'id="naver-as"' in html and "A/S 전화번호" in html
    assert 'data-account="chezgoga"' in html and 'data-account="gocosmos"' in html
    box = html.split('id="naver-as"')[1].split('data-action="naver-as-save"')[0]
    assert "서버 기본값" in box and "NAVER_" not in box                                  # 화면에 env 이름 0
    r = c.post("/seller/markets/naver-as", json={"values": {"chezgoga": "010-2222-3333", "evil": "1"}})
    d = r.get_json()
    assert d["ok"] and [x["source"] for x in d["rows"]] == ["설정", "서버 기본값"]
    assert c.post("/seller/markets/naver-as", json={"values": {"chezgoga": "abc"}}).status_code == 400
    from src.uploaders import naver_as as NAS
    assert NAS.get_all(shared=True) == {"chezgoga": "010-2222-3333"}                    # 공유 사용자 한 벌
    # 같은 요청 문맥(공유 사용자)에서 사전검증이 그 값을 쓴다
    with app.test_request_context():
        from flask import session
        session.update(user_id="y7l", user_email=FAM)
        assert _as_codes("chezgoga") == []


def test_regular_seller_has_one_row_and_cannot_write_shared_stores(naver):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7l-solo", user_email="solo@example.com", user_role="seller")
    html = c.get("/seller/markets/connect/smartstore").get_data(as_text=True)
    assert 'data-account="default"' in html and 'data-account="chezgoga"' not in html
    assert c.post("/seller/markets/naver-as", json={"values": {"chezgoga": "010-1111-2222"}}).status_code == 400


def test_link_scrolls_to_the_field():
    from pathlib import Path
    t = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    assert "location.hash !== '#naver-as'" in t and "box.scrollIntoView" in t and "first.focus" in t
