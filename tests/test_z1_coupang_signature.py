"""Z1(오너 2026-10-04) — 우주대행 「불러오기」가 쿠팡 401 Invalid signature(04:48 · 18:06).

계약: 서명 직전 **실제로 읽은 이름**을 드러내고, 키 쌍이 섞이거나 한 키가 두 이름에 다른 값이면 서명 전에 막는다.
가짜 게이트웨이가 HMAC을 **진짜로 검증**한다(액세스 키 → 등록된 시크릿으로 다시 계산해 비교).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re

import pytest

PAIRS = {"gogane-ak-0001": "gogane-secret", "woojoo-ak-0002": "woojoo-secret"}
CALLS = []


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body, ensure_ascii=False)
        self.content = self.text.encode()
        self.headers = {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _gateway(method, url, headers=None, **kw):
    """쿠팡 CEA 검증: message = signed-date + method + path + query(물음표 없이)."""
    CALLS.append(url)
    auth = (headers or {}).get("Authorization", "")
    m = re.search(r"access-key=([^,]+), signed-date=([^,]+), signature=(\w+)", auth)
    path = url.split("api-gateway.coupang.com", 1)[1]
    secret = PAIRS.get(m.group(1)) if m else None
    if not secret:
        return _Resp(401, {"code": "ERROR", "message": "Invalid access key."})
    want = hmac.new(secret.encode(), (m.group(2) + method + path.replace("?", "", 1)).encode(), hashlib.sha256).hexdigest()
    if want != m.group(3):
        return _Resp(401, {"code": "ERROR", "message": "Invalid signature."})
    return _Resp(200, {"code": "SUCCESS", "data": {"content": [{"returnCenterCode": "R1", "shippingPlaceName": "반품지"}]}})


@pytest.fixture
def env(monkeypatch):
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID", "COUPANG_WOOJOO_ACCESS",
              "COUPANG_WOOJOO_SECRET", "COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "gogane-ak-0001")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "gogane-secret")
    monkeypatch.setenv("COUPANG_VENDOR_ID", "A01381223")
    monkeypatch.setenv("COUPANG_WOOJOO_ACCESS_KEY", "woojoo-ak-0002")
    monkeypatch.setenv("COUPANG_WOOJOO_SECRET_KEY", "woojoo-secret")
    monkeypatch.setenv("COUPANG_WOOJOO_VENDOR_ID", "A01504840")
    import src.uploaders.coupang_uploader as U
    monkeypatch.setattr(U, "relay_request", _gateway)
    CALLS.clear()
    return monkeypatch


def test_woojoo_pair_signs_and_gets_200(env):
    from src.seller_console.coupang_shipping_lookup import fetch
    out = fetch("woojoo")
    assert out["return_centers"]["ok"], out
    assert any("/vendors/A01504840/returnShippingCenters" in u for u in CALLS)


def test_the_two_accounts_sign_the_same_request_with_their_own_keys(env):
    from src.pipeline.coupang_replicate import _account_creds
    from src.uploaders.coupang_uploader import CoupangUploader
    msgs = {}
    for acct in ("gogane", "woojoo"):
        a, s, v = _account_creds(acct)
        up = CoupangUploader(access_key=a, secret_key=s, vendor_id=v, account=acct)
        up._api_request("GET", "/v2/providers/openapi/apis/api/v5/vendors/X/returnShippingCenters")
        msgs[acct] = up.last_sign
    assert msgs["gogane"]["access_tail"].startswith("…0001") and msgs["woojoo"]["access_tail"].startswith("…0002")
    assert msgs["gogane"]["status"] == msgs["woojoo"]["status"] == 200
    assert "gogane-secret" not in json.dumps(msgs) and "woojoo-secret" not in json.dumps(msgs)   # 서명문에 시크릿 없음


def test_one_key_under_two_names_with_different_values_is_blocked_before_sending(env):
    env.setenv("COUPANG_WOOJOO_SECRET", "old-secret")
    from src.seller_console.coupang_shipping_lookup import fetch
    out = fetch("woojoo")
    assert not out["ok"] and CALLS == []                                      # 쿠팡에 안 보냄
    err = out["reason"]
    assert "COUPANG_WOOJOO_SECRET_KEY" in err and "COUPANG_WOOJOO_SECRET" in err and "다른 값" in err


def test_mixed_prefix_pair_is_blocked(env):
    """고가네: 접두 액세스 + 무접두 시크릿 = 섞인 쌍 → 「키 쌍 불일치」로 서명 전 차단."""
    env.setenv("COUPANG_GOGANE_ACCESS_KEY", "woojoo-ak-0002")
    from src.pipeline.coupang_replicate import _account_creds, account_cred_problem
    assert _account_creds("gogane")[:2] == ("", "")
    assert "키 쌍 불일치" in account_cred_problem("gogane")
    assert "COUPANG_GOGANE_ACCESS_KEY" in account_cred_problem("gogane")


def test_woojoo_never_falls_back_to_unprefixed_keys(env):
    env.delenv("COUPANG_WOOJOO_SECRET_KEY")
    from src.pipeline.coupang_replicate import _account_creds, coupang_key_source
    a, s, _v = _account_creds("woojoo")
    assert a == "woojoo-ak-0002" and s == ""                                  # 무접두 gogane-secret 안 씀
    ks = coupang_key_source("woojoo")
    assert ks["secret_env"] == "" and not ks["ready"]


def test_quoted_secret_is_blocked(env):
    env.setenv("COUPANG_WOOJOO_SECRET_KEY", '"woojoo-secret"')
    from src.pipeline.coupang_replicate import account_cred_problem
    assert "따옴표·공백" in account_cred_problem("woojoo")


def test_401_names_the_keys_that_signed(env):
    env.setenv("COUPANG_WOOJOO_SECRET_KEY", "wrong-but-clean")
    from src.seller_console.coupang_shipping_lookup import fetch
    err = fetch("woojoo")["return_centers"]["error"]
    assert "Invalid signature" in err and "COUPANG_WOOJOO_ACCESS_KEY" in err and "COUPANG_WOOJOO_SECRET_KEY" in err
    assert "wrong-but-clean" not in err                                       # 값은 안 싣는다


def test_diagnostics_compare_page(env):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/coupang-sign").get_data(as_text=True)
    assert h.count('data-role="coupang-sign-row"') == 2 and "HTTP 200" in h
    assert "COUPANG_WOOJOO_ACCESS_KEY" in h and "…0002" in h
    assert "woojoo-secret" not in h and "gogane-secret" not in h
