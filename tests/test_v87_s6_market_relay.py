"""tests/test_v87_s6_market_relay.py — v87-S6-2: 마켓 API 고정 IP 릴레이(mkt.php) 분기.

■ 왜 필요한가
쿠팡 WING·네이버 커머스는 **호출 IP 화이트리스트**를 요구하는데 Render는 아웃바운드 IP가 고정이 아니다.
오너가 Bluehost(50.6.34.63)에 mkt.php 릴레이를 설치했으므로, 서명까지 끝난 요청을 그쪽으로 넘겨
고정 IP에서 실제 호출하게 한다.

■ 프로토콜(오너 확정)
POST {url, method, headers, body_b64} + 헤더 X-KGP-Relay-Key → {status, content_type, body_b64}

■ 이 파일이 지키는 계약(브리프 3종)
1. 직결/릴레이 분기 — MARKET_API_RELAY_URL 있으면 경유, 없으면 현행 직결(회귀 0).
2. **서명은 원 URL 기준** — 릴레이 URL로 서명하면 쿠팡 CEA 서명이 깨진다(path+query로 서명하므로).
   릴레이는 헤더를 무가공 전달해야 하고, 우리가 보내는 payload의 url도 원 URL이어야 한다.
3. 허용 외 호스트는 **클라이언트 단에서도** 거부 — 릴레이의 화이트리스트에만 기대지 않는다.
"""
from __future__ import annotations

import base64
import json

import pytest
import requests

from src import market_relay


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("MARKET_API_RELAY_URL", "MARKET_API_RELAY_KEY", "MARKET_RELAY_URL", "MARKET_RELAY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    # 스로틀 페이싱이 테스트를 늦추지 않게(호출 계약만 본다).
    monkeypatch.setattr(market_relay, "throttled_request", None, raising=False)


COUPANG_URL = "https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
NAVER_URL = "https://api.commerce.naver.com/external/v1/products"


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code), response=self)


# ── 1. 직결 / 릴레이 분기 ─────────────────────────────────────────────────────

def test_direct_call_when_relay_not_configured(monkeypatch):
    """MARKET_API_RELAY_URL 미설정 → 마켓으로 직결(기존 동작 유지)."""
    seen = {}

    def fake_request(method, url, **kw):
        seen["method"], seen["url"] = method, url
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("릴레이로 갔다 — 직결이어야 한다"))

    resp = market_relay.relay_request("POST", COUPANG_URL, json={"a": 1}, headers={"Authorization": "CEA x"},
                                      market="coupang")
    assert resp.status_code == 200
    assert seen["url"] == COUPANG_URL, "직결인데 URL이 바뀌었다"


def test_relay_used_when_configured(monkeypatch):
    """MARKET_API_RELAY_URL 설정 → 전 요청이 릴레이 경유 + 프로토콜 형태가 맞다."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    monkeypatch.setenv("MARKET_API_RELAY_KEY", "s3cret")
    monkeypatch.setattr(requests, "request", lambda *a, **k: pytest.fail("직결로 샜다 — 릴레이여야 한다"))
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        seen.update(url=url, payload=json, headers=headers, timeout=timeout)
        return _Resp(200, {"status": 201, "content_type": "application/json",
                           "body_b64": base64.b64encode(b'{"data":7}').decode()})

    monkeypatch.setattr(requests, "post", fake_post)

    resp = market_relay.relay_request("POST", COUPANG_URL, json={"a": 1},
                                      headers={"Authorization": "CEA sig"}, market="coupang")

    assert seen["url"] == "https://relay.example.com/mkt.php"
    assert seen["headers"]["X-KGP-Relay-Key"] == "s3cret", "공유 시크릿 헤더가 없다"
    assert seen["timeout"] == 35, "타임아웃 35s 계약"
    p = seen["payload"]
    assert set(p) == {"url", "method", "headers", "body_b64"}, p
    assert p["method"] == "POST"
    assert json.loads(base64.b64decode(p["body_b64"])) == {"a": 1}
    # 응답은 릴레이 봉투를 풀어 마켓 응답 그대로 돌려준다.
    assert resp.status_code == 201
    assert resp.json() == {"data": 7}


def test_relay_envelope_sends_branded_ua_not_python_requests(monkeypatch):
    """v87-S8: 릴레이 봉투에 UA·Accept 명시.

    requests 기본 UA(`python-requests/x.y.z`)는 Bluehost Apache mod_security가 406 'Not Acceptable'로
    끊는다(실측: UA만 바꾸면 406→403으로 스크립트까지 도달). 이 프로젝트의 WooCommerce 406도 같은
    원인이었으므로 재발 방지로 못박는다.
    """
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        seen.update(headers=headers, payload=json)
        return _Resp(200, {"status": 200, "body_b64": ""})

    monkeypatch.setattr(requests, "post", fake_post)
    market_relay.relay_request("POST", NAVER_URL, data={"grant_type": "client_credentials"},
                               market="smartstore")

    h = {k.lower(): v for k, v in seen["headers"].items()}
    assert "user-agent" in h, "봉투에 UA가 없다 — 기본 python-requests UA로 나가 406에 걸린다"
    assert "python-requests" not in h["user-agent"].lower(), h["user-agent"]
    assert "gogabridj" in h["user-agent"].lower(), h["user-agent"]
    assert h.get("accept") == "application/json", h.get("accept")


def test_relay_ua_is_not_injected_into_market_request_headers(monkeypatch):
    """UA는 **봉투에만**. 마켓 원 요청 헤더에 끼워넣으면 서명 대상 헤더가 오염된다."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        seen.update(payload=json)
        return _Resp(200, {"status": 200, "body_b64": ""})

    monkeypatch.setattr(requests, "post", fake_post)
    market_relay.relay_request("POST", NAVER_URL, headers={"Authorization": "Bearer T"},
                               data={"a": 1}, market="smartstore")

    inner = {k.lower() for k in seen["payload"]["headers"]}
    assert "user-agent" not in inner, f"마켓 요청 헤더가 오염됐다: {seen['payload']['headers']}"
    assert seen["payload"]["headers"]["Authorization"] == "Bearer T", "원 헤더가 변형됐다"


def test_naver_host_also_relayed(monkeypatch):
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _Resp(200, {"status": 200, "body_b64": ""}))
    resp = market_relay.relay_request("GET", NAVER_URL, headers={}, market="smartstore")
    assert resp.status_code == 200


# ── 2. 서명은 원 URL 기준(릴레이 URL 아님) ────────────────────────────────────

def test_signature_is_built_over_original_url_not_relay(monkeypatch):
    """★ 쿠팡 CEA 서명은 path+query로 만든다 — 릴레이 URL로 서명하면 깨진다.

    업로더가 **relay_request 호출 전에** 원 path로 서명하고, 릴레이 payload의 url도 원 URL이어야 한다.
    """
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    from src.uploaders.coupang_uploader import CoupangUploader

    up = CoupangUploader()
    up.access_key, up.secret_key, up.vendor_id = "AK", "SK", "V1"
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products?nextToken=2"
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured.update(payload=json)
        return _Resp(200, {"status": 200, "body_b64": base64.b64encode(b"{}").decode()})

    monkeypatch.setattr(requests, "post", fake_post)
    up._api_request("GET", path)

    sent = captured["payload"]
    assert sent["url"].startswith("https://api-gateway.coupang.com"), "원 URL이 아니라 릴레이 URL을 보냈다"
    assert "nextToken=2" in sent["url"], "쿼리가 날아갔다 — 쿠팡 서명은 쿼리를 포함한다"
    assert "relay.example.com" not in sent["url"]

    # 서명 문자열이 원 path 기준인지 직접 대조(릴레이 URL 기준이면 불일치).
    auth = sent["headers"]["Authorization"]
    signed_date = auth.split("signed-date=")[1].split(",")[0].strip()
    expected = up._generate_hmac_signature("GET", path, signed_date)
    assert f"signature={expected}" in auth, "서명이 원 URL(path+query) 기준이 아니다"


# ── 3. 허용 외 호스트는 클라이언트 단에서도 거부 ──────────────────────────────

@pytest.mark.parametrize("bad", [
    "https://evil.example.com/steal",
    "https://api-gateway.coupang.com.evil.com/x",   # 접미사 위장
    "http://localhost:8080/internal",
])
def test_disallowed_host_refused_client_side(monkeypatch, bad):
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("허용 외 호스트가 릴레이로 나갔다"))
    with pytest.raises(market_relay.RelayError) as exc:
        market_relay.relay_request("POST", bad, json={}, market="coupang")
    assert "허용되지 않은 호스트" in str(exc.value)


def test_allowlist_is_exact_host_match():
    assert market_relay.assert_host_allowed(COUPANG_URL) == "api-gateway.coupang.com"
    with pytest.raises(market_relay.RelayError):
        market_relay.assert_host_allowed("https://coupang.com/x")


# ── 릴레이 오류는 마켓 오류와 구분해 정직 표기 ────────────────────────────────

def test_relay_failure_is_labelled_distinctly_not_as_market_error(monkeypatch):
    """릴레이가 죽은 것과 쿠팡이 거부한 것을 마켓 카드에서 구분할 수 있어야 한다."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")
    from src.uploaders.coupang_uploader import CoupangUploader

    up = CoupangUploader()
    up.access_key, up.secret_key, up.vendor_id = "AK", "SK", "V1"
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(502, {}))

    out = up._api_request("GET", "/v2/x")
    assert "릴레이 오류" in out.get("error", ""), out
    assert "502" in out["error"]


def test_relay_error_message_mentions_unreachable(monkeypatch):
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.com/mkt.php")

    def boom(*a, **k):
        raise requests.exceptions.ConnectTimeout("no route")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(market_relay.RelayError) as exc:
        market_relay.relay_request("POST", COUPANG_URL, json={}, market="coupang")
    assert "릴레이 오류" in str(exc.value)
