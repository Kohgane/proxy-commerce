"""tests/test_register_pipe_p2.py — 등록 파이프 P2: 계정별 배송 env + 구매대행(PCCC) 페이로드.

CoupangUploader의 계정 접두 배송 env 라우팅(COUPANG_GOGANE_*/COUPANG_WOOJOO_*)과
해외구매대행 통관(pccNeeded·고시정보)을 오프라인으로 계약 검증(라이브 쿠팡 호출 0).
"""
from __future__ import annotations

from src.uploaders.coupang_uploader import CoupangUploader

_SHIP_SUFFIXES = ["VENDOR_USER_ID", "RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE",
                  "RETURN_ZIP_CODE", "RETURN_ADDRESS", "RETURN_CHARGE_NAME", "COMPANY_CONTACT_NUMBER"]


def _set_prefixed(monkeypatch, prefix, tag):
    for s in _SHIP_SUFFIXES:
        monkeypatch.setenv(f"{prefix}_{s}", f"{tag}-{s}")


def test_account_prefixed_shipping_env_routes(monkeypatch):
    # 고가네/우주대행 각각 접두 배송 env를 읽는다(계정 라우팅).
    _set_prefixed(monkeypatch, "COUPANG_GOGANE", "gogane")
    _set_prefixed(monkeypatch, "COUPANG_WOOJOO", "woojoo")
    g = CoupangUploader(access_key="a", secret_key="b", vendor_id="A01381223", account="gogane")
    w = CoupangUploader(access_key="a", secret_key="b", vendor_id="A01504840", account="woojoo")
    assert g.return_center_code == "gogane-RETURN_CENTER_CODE"
    assert w.return_center_code == "woojoo-RETURN_CENTER_CODE"
    assert g.vendor_user_id == "gogane-VENDOR_USER_ID"
    assert not g._missing_shipping_config() and not w._missing_shipping_config()


def test_woojoo_does_not_borrow_gogane_unprefixed(monkeypatch):
    # 우주대행 접두 미설정 + 무접두는 고가네 소유(base account) → 우주대행이 무접두를 도용하지 않는다(혼입 방지).
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "x")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "y")
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A01381223")   # 무접두 = 고가네 vendor
    monkeypatch.setenv("COUPANG_RETURN_CENTER_CODE", "GOGANE_UNPREFIXED")
    w = CoupangUploader(access_key="a", secret_key="b", vendor_id="A01504840", account="woojoo")
    assert w.return_center_code == ""                       # 우주대행은 고가네 무접두를 빌리지 않음
    missing = w._missing_shipping_config()
    assert any("COUPANG_WOOJOO_RETURN_CENTER_CODE" == m for m in missing)   # 접두 키명으로 정직 안내
    # base account(고가네)는 무접두 폴백 허용.
    g = CoupangUploader(access_key="a", secret_key="b", vendor_id="A01381223", account="gogane")
    assert g.return_center_code == "GOGANE_UNPREFIXED"


def test_no_account_reads_unprefixed_backward_compat(monkeypatch):
    # account 미지정 = 기존 무접두 동작(무회귀).
    monkeypatch.setenv("COUPANG_RETURN_CENTER_CODE", "PLAIN")
    u = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    assert u.return_center_code == "PLAIN" and u.account is None


def test_overseas_purchased_sets_pcc_and_notices(monkeypatch):
    # 구매대행 → overseasPurchased + pccNeeded + 통관 고시정보(원산지 해외·수입자 구매대행).
    u = CoupangUploader(access_key="a", secret_key="b", vendor_id="v", overseas_purchased=True)
    assert u.overseas_purchased is True
    payload = u._build_product_payload({"title": "니치 백팩", "price": 50000, "images": ["u"]})
    item = payload["items"][0]
    assert item["overseasPurchased"] == "OVERSEAS_PURCHASED" and item["pccNeeded"] is True
    notices = {n["noticeCategoryDetailName"]: n["content"] for n in item["notices"]}
    origin = [v for k, v in notices.items() if "제조국" in k or "원산지" in k]
    assert origin and "해외" in origin[0]                    # 원산지 해외(구매대행) 정직 표기
    importer = [v for k, v in notices.items() if "제조자" in k or "수입자" in k]
    assert importer and "개인통관고유부호" in importer[0]      # PCCC 통관 안내


def test_non_overseas_default_no_pcc(monkeypatch):
    # 명시 안 하면 env 기본(0) → 일반 상품(pccNeeded False) 무회귀.
    monkeypatch.delenv("COUPANG_OVERSEAS_PURCHASED", raising=False)
    u = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    payload = u._build_product_payload({"title": "국내 상품", "price": 10000, "images": ["u"]})
    assert payload["items"][0]["pccNeeded"] is False
