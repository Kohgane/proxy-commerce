"""tests/test_delivery_company_code.py — 카나리 6차 거부: 유효하지 않은 택배사 코드(DIRECT_DELIVERY).

정본 = 쿠팡 메타 API 목록(발명 금지) + 계정별 env(하드코딩 금지). 미확정이면 등록 전 정직 실패.
"""
from __future__ import annotations

from src.uploaders.coupang_uploader import CoupangUploader

_SHIP = ("VENDOR_USER_ID", "RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE",
         "RETURN_ZIP_CODE", "RETURN_ADDRESS", "RETURN_CHARGE_NAME", "COMPANY_CONTACT_NUMBER")
_COMPANIES = {"data": [{"deliveryCompanyCode": "EPOST", "deliveryCompanyName": "우체국택배"},
                       {"deliveryCompanyCode": "CJGLS", "deliveryCompanyName": "CJ대한통운"}]}


def _up(monkeypatch, account=None, **env):
    # 계정 지정 시엔 **접두** 배송 env가 필요(P2 계정 간 혼입 방지 — 무접두는 소유 계정만 폴백).
    pfx = {"gogane": "COUPANG_GOGANE", "woojoo": "COUPANG_WOOJOO"}.get(account or "", "COUPANG")
    for s in _SHIP:
        monkeypatch.setenv(f"COUPANG_{s}", "x")
        monkeypatch.setenv(f"{pfx}_{s}", "x")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return CoupangUploader(access_key="a", secret_key="b", vendor_id="v", account=account)


def _wire(monkeypatch, up, sent=None):
    def _api(m, p, data=None):
        if "coupang-delivery-companies" in p:
            return _COMPANIES
        if "categorization/predict" in p:
            return {"data": {"predictedCategoryId": "1001"}}
        if m == "POST" and "seller-products" in p:
            if sent is not None:
                sent["payload"] = data
            return {"data": 1, "code": "SUCCESS"}
        return {}
    monkeypatch.setattr(up, "_api_request", _api)


def test_no_hardcoded_direct_delivery_in_source():
    # 하드코딩 금지 — 소스에 DIRECT_DELIVERY 상수 잔존 0(거부 원인 제거).
    src = open("src/uploaders/coupang_uploader.py", encoding="utf-8").read()
    assert "'DIRECT_DELIVERY'" not in src and '"DIRECT_DELIVERY"' not in src


def test_env_code_is_used_verbatim(monkeypatch):
    # ① env 코드(기존 스크립트 정본 승계) 우선 — API 조회 없이 그대로 전송.
    up = _up(monkeypatch, account="gogane", COUPANG_GOGANE_DELIVERY_COMPANY_CODE="EPOST")
    sent = {}
    _wire(monkeypatch, up, sent)
    r = up.upload_product({"title": "케이스", "brand": "B", "origin": "중국", "sku": "s", "images": ["u"]})
    assert r["success"] is True
    assert sent["payload"]["deliveryCompanyCode"] == "EPOST"


def test_name_hint_resolves_from_coupang_list(monkeypatch):
    # ② 코드 모르면 이름 힌트(Wing 실측 '우체국')로 **쿠팡 목록에서** 매칭 — 발명 0.
    up = _up(monkeypatch, account="gogane", COUPANG_GOGANE_DELIVERY_COMPANY_NAME="우체국")
    sent = {}
    _wire(monkeypatch, up, sent)
    r = up.upload_product({"title": "케이스", "brand": "B", "origin": "중국", "sku": "s", "images": ["u"]})
    assert r["success"] is True
    assert sent["payload"]["deliveryCompanyCode"] == "EPOST"      # 목록의 '우체국택배' 코드


def test_unset_holds_before_send(monkeypatch):
    # ③ 코드·이름 모두 없음 → 등록 전 정직 실패(유효하지 않은 코드 전송 0 = 카나리 재소모 방지).
    up = _up(monkeypatch, account="woojoo")
    sent = {}
    _wire(monkeypatch, up, sent)
    r = up.upload_product({"title": "케이스", "brand": "B", "origin": "중국", "sku": "s", "images": ["u"]})
    assert r["success"] is False and r.get("held") is True
    assert "COUPANG_WOOJOO_DELIVERY_COMPANY_CODE" in r["error"]   # 계정 접두 키명 안내
    assert "sent" not in sent and not sent                        # POST 호출 0


def test_account_specific_codes(monkeypatch):
    # 계정별 상이 가능 — 접두 env가 각각 적용.
    monkeypatch.setenv("COUPANG_GOGANE_DELIVERY_COMPANY_CODE", "EPOST")
    monkeypatch.setenv("COUPANG_WOOJOO_DELIVERY_COMPANY_CODE", "CJGLS")
    g = _up(monkeypatch, account="gogane")
    w = _up(monkeypatch, account="woojoo")
    assert g.resolve_delivery_company_code() == "EPOST"
    assert w.resolve_delivery_company_code() == "CJGLS"


def test_delivery_method_and_charge_type_env(monkeypatch):
    # 배송 방식·배송비 유형도 env화(같은 스크립트 승계용) — 기본값은 기존 동작 유지(무회귀).
    up = _up(monkeypatch, account="gogane", COUPANG_GOGANE_DELIVERY_COMPANY_CODE="EPOST")
    assert up.delivery_method == "SEQUENCIAL" and up.delivery_charge_type == "FREE"
    up2 = _up(monkeypatch, account="gogane", COUPANG_GOGANE_DELIVERY_COMPANY_CODE="EPOST",
              COUPANG_GOGANE_DELIVERY_METHOD="AGENT_BUY", COUPANG_GOGANE_DELIVERY_CHARGE_TYPE="NOT_FREE")
    sent = {}
    _wire(monkeypatch, up2, sent)
    up2.upload_product({"title": "x", "brand": "B", "origin": "중국", "sku": "s", "images": ["u"]})
    assert sent["payload"]["deliveryMethod"] == "AGENT_BUY"
    assert sent["payload"]["deliveryChargeType"] == "NOT_FREE"


def test_get_delivery_companies_parses_and_caches(monkeypatch):
    up = _up(monkeypatch, account="gogane")
    calls = {"n": 0}
    def _api(m, p, data=None):
        calls["n"] += 1
        return _COMPANIES
    monkeypatch.setattr(up, "_api_request", _api)
    rows = up.get_delivery_companies()
    assert {"code": "EPOST", "name": "우체국택배"} in rows
    up.get_delivery_companies()
    assert calls["n"] == 1                                        # 1회 조회 후 캐시


def test_admin_route_lists_codes(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    for s in _SHIP:
        monkeypatch.setenv(f"COUPANG_GOGANE_{s}", "x")
    monkeypatch.setenv("COUPANG_GOGANE_ACCESS_KEY", "a")
    monkeypatch.setenv("COUPANG_GOGANE_SECRET_KEY", "b")
    monkeypatch.setenv("COUPANG_GOGANE_DELIVERY_COMPANY_NAME", "우체국")
    import src.dashboard.admin_views as AV
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    monkeypatch.setattr(CU, "get_delivery_companies",
                        lambda self: [{"code": "EPOST", "name": "우체국택배"}])
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"; s["user_email"] = "shanks8@hanmail.net"; s["user_role"] = "admin"
    d = c.get("/admin/coupang-delivery-companies?account=gogane").get_json()
    assert d["ok"] is True and d["count"] == 1
    assert d["companies"][0]["code"] == "EPOST" and d["current_code"] == "EPOST"
