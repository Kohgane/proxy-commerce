"""오너 11-26 저녁 ③ — 쿠팡 사전검증 보류를 폰 카드 안에서 채운다(필수 옵션 · 옵션 값 · 원산지) 계약.

보류 줄(쿠팡 판정 원문)을 읽어 고치는 길·입력칸으로 · 모르는 줄은 그대로(fix 없음) · 계정 칸(출고지·인보이스)은 어디서 채우는지만.
저장은 넣은 칸만 합친다(다른 칸 그대로) · 전송 0.
"""
from __future__ import annotations

import json

import pytest


def test_parse_known_lines_only():
    from src.uploaders.coupang_hold_fix import parse
    fixes, fields = parse([
        "필수 옵션: 용량, 개당 수량",
        "필수 옵션(택1): 색상 또는 모델명 — 옵션에 없어요",
        "옵션 값 미해석: 黑色 — 번역 결과 없음",
        "옵션 값 2개를 한국어로 옮기지 못했습니다 — 값을 직접 넣거나 번역을 먼저 돌려 주세요: 红色, 蓝色",
        "「용량」 단위가 없습니다(ml·L)",
        "「색상」 값이 3개입니다 — 여러 옵션 등록은 SKU별 가격이 필요합니다",
        "고시정보 실값 미확인(제조국(원산지)) — 등록 보류(추정 금지, 원산지 등 확인 필요)",
        "구매대행 출고지는 해외 주소지만 받습니다 — 「구매대행 출고지 (해외)」가 비어 있습니다.",
        "구매대행 필수 서류 「인보이스」의 파일 URL이 없습니다 — 인보이스 URL은 오너 결정 사항입니다(결정 전까지 전송 보류).",
        "쿠팡 카테고리 예측 실패 — 임의 카테고리 전송 금지.",
        "알 수 없는 새 사유",
    ])
    assert fixes == ["cp_attr", "cp_value", "edit-option", "cp_origin", "cp_outbound", "cp_invoice", "cp_category"]
    kinds = [(f["kind"], f.get("name") or f.get("names") or f.get("orig")) for f in fields]
    assert kinds == [("attr", "용량"), ("attr", "개당 수량"), ("attr_one", ["색상", "모델명"]), ("value", "黑色"),
                     ("value", "红色"), ("value", "蓝色"), ("origin", None)]
    assert parse(["알 수 없는 새 사유"]) == ([], [])


def test_prevalidate_result_carries_fields():
    from src.seller_console import views as V
    from src.seller_console.upload_dispatcher import PrevalidationResult
    row = V._pv_dict(PrevalidationResult(market="coupang", ok=False, error_code="coupang_hold", fixes=["cp_attr"],
                                         cp_fields=[{"kind": "attr", "name": "용량"}]))
    assert row["cp_fields"] == [{"kind": "attr", "name": "용량"}] and row["fixes"] == ["cp_attr"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def test_save_merges_only_given_and_builder_reads_them(client):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE", price="1", currency="KRW", image="",
                   seller_id="default", extra={"title_ko": "칼", "coupang_attributes": [{"attributeTypeName": "색상", "attributeValueName": "검정"}],
                                               "option_value_overrides": {"红色": "빨강"}})
    assert client.post(f"/seller/collect/{iid}/coupang-fields", json={}).status_code == 400
    d = client.post(f"/seller/collect/{iid}/coupang-fields", json={"attributes": [{"name": "용량", "value": "500ml"}, {"name": "x", "value": ""}],
                                                                  "value_overrides": {"黑色": "검정"}, "origin": "중국"}).get_json()
    assert d["ok"] and d["saved"] == ["필수 옵션 1칸", "옵션 값 1개", "원산지"]
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert {a["attributeTypeName"] for a in ex["coupang_attributes"]} == {"용량", "색상"}
    assert ex["option_value_overrides"] == {"红色": "빨강", "黑色": "검정"} and ex["origin"] == "중국" and ex["title_ko"] == "칼"
    from src.seller_console.product_builder import build_product
    pd = build_product(S.get(iid, seller_id="default"), seller_id="default")
    assert pd["origin"] == "중국" and {"attributeTypeName": "용량", "attributeValueName": "500ml"} in pd["coupang_attributes"]


def test_card_js_renders_inputs_and_account_links(client):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE", price="1", currency="KRW", image="",
                   seller_id="default", extra={"title_ko": "칼"})
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    for needle in ("function cpFieldsHtml", "data-role=\"m5-cp-fields\"", "m5-cp-save", "/coupang-fields", "쿠팡 출고지 넣기(마켓 연동)",
                   "구매대행 인보이스 주소는 계정 설정이에요", "has('cp_category')", "runCheck([b.getAttribute('data-market')], true)",
                   "if (r.hold || r.error_code === 'coupang_hold') h += holdFixHtml(r, h);"):
        assert needle in h, needle
