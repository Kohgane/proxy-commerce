"""tests/test_v87_s7_naver_token_relay.py — v87-S7: 네이버 토큰 발급도 릴레이 경유 + 단일 관문.

■ 오너 실측(재조사 금지)
- 쿠팡 read+dry-run 그린(50.6.34.63 경유) = 릴레이 자체는 가동.
- 스마트스토어는 같은 시각 재시도에서 GW.IP_NOT_ALLOWED. 커머스API센터에 50.6.34.63이 등록돼 있고
  api.commerce.naver.com도 릴레이 허용 호스트에 있는데도 막혔다 → **토큰 발급 요청이 직결로 나갔다는 물증**.

■ 근본
상품 API만 relay_request를 타고 **OAuth 토큰 발급 3곳이 requests.post 직결**이었다. 토큰을 못 받으면
그 뒤 모든 호출이 연쇄 실패하므로, 겉으로는 "스마트스토어 전체가 IP 차단"처럼 보인다.

■ 계약
1. env 설정 상태에서 네이버 토큰 발급이 **릴레이 URL로** 나간다(3개 경로 전부).
2. 마켓 아웃바운드 모듈에 **직결 requests 호출 잔존 0** — 이번 같은 누락이 구조적으로 재발하지 않게.
3. 폼 인코딩 보존 — 토큰 발급은 form 전송이라 JSON으로 바뀌면 릴레이 너머에서 조용히 깨진다.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import parse_qs

import pytest
import requests

from src import market_relay

RELAY = "https://relay.example.com/mkt.php"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("MARKET_API_RELAY_URL", "MARKET_API_RELAY_KEY", "MARKET_RELAY_URL", "MARKET_RELAY_TOKEN"):
        monkeypatch.delenv(k, raising=False)


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}
        import json as _j
        self.text = _j.dumps(self._p)

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code), response=self)


def _token_relay_capture(monkeypatch):
    """릴레이로 나간 payload를 잡아두고, 네이버 토큰 응답을 흉내낸다."""
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        seen.update(url=url, payload=json, headers=headers)
        body = base64.b64encode(b'{"access_token":"TK","expires_in":3600}').decode()
        return _Resp(200, {"status": 200, "content_type": "application/json", "body_b64": body})

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "request",
                        lambda *a, **k: pytest.fail("토큰 발급이 직결로 샜다"))
    return seen


# ── 1. 토큰 발급 3경로가 릴레이로 나간다 ──────────────────────────────────────

def test_naver_uploader_token_goes_through_relay(monkeypatch):
    monkeypatch.setenv("MARKET_API_RELAY_URL", RELAY)
    seen = _token_relay_capture(monkeypatch)
    from src.uploaders.naver_uploader import NaverSmartStoreUploader

    up = NaverSmartStoreUploader()
    up.client_id, up.client_secret = "CID", "CSEC"
    up._access_token, up._token_expires = "", 0
    assert up._get_access_token() == "TK"

    assert seen["url"] == RELAY, "토큰 발급이 릴레이로 안 갔다"
    assert seen["payload"]["url"].startswith("https://api.commerce.naver.com"), seen["payload"]["url"]


def test_smartstore_adapter_token_goes_through_relay(monkeypatch):
    """★ 오너가 '재시도'로 누르는 콘솔 경로 — 여기가 직결이라 GW.IP_NOT_ALLOWED가 났다."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", RELAY)
    seen = _token_relay_capture(monkeypatch)
    from src.seller_console.market_adapters import smartstore_adapter as ss

    monkeypatch.setattr(ss, "_naver_signature", lambda *a, **k: "SIGN", raising=False)
    ss._token_cache.clear()
    monkeypatch.setenv("NAVER_CLIENT_ID", "CID")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "$2a$04$abcdefghijklmnopqrstuv")

    token = ss._get_access_token()
    assert token == "TK", ss._token_cache.get("last_error")
    assert seen["url"] == RELAY, "콘솔 어댑터 토큰 발급이 릴레이로 안 갔다"


def test_naver_commerce_auth_token_goes_through_relay(monkeypatch):
    monkeypatch.setenv("MARKET_API_RELAY_URL", RELAY)
    seen = _token_relay_capture(monkeypatch)
    from src.markets.adapters import naver_commerce_auth as nca

    nca._TOKEN_CACHE.clear()
    monkeypatch.setattr(nca, "_build_client_secret_sign", lambda *a, **k: "SIGN", raising=False)
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "CID")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "$2a$04$abcdefghijklmnopqrstuv")
    assert nca.get_access_token(force_refresh=True) == "TK"
    assert seen["url"] == RELAY


# ── 3. 폼 인코딩 보존(릴레이 너머에서 네이버가 읽을 수 있어야) ────────────────

def test_token_body_is_form_encoded_not_json(monkeypatch):
    """네이버 토큰은 x-www-form-urlencoded다. JSON으로 바꿔 보내면 조용히 실패한다."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", RELAY)
    seen = _token_relay_capture(monkeypatch)
    from src.uploaders.naver_uploader import NaverSmartStoreUploader

    up = NaverSmartStoreUploader()
    up.client_id, up.client_secret = "CID", "CSEC"
    up._access_token, up._token_expires = "", 0
    up._get_access_token()

    body = base64.b64decode(seen["payload"]["body_b64"]).decode()
    assert not body.lstrip().startswith("{"), f"JSON으로 나갔다: {body[:60]}"
    form = parse_qs(body)
    assert form["grant_type"] == ["client_credentials"], form
    assert form["client_id"] == ["CID"], form
    ct = {k.lower(): v for k, v in seen["payload"]["headers"].items()}.get("content-type", "")
    assert "x-www-form-urlencoded" in ct, ct


# ── 2. 마켓 아웃바운드에 직결 requests 잔존 0 (구조적 재발 방지) ──────────────

_MARKET_OUTBOUND = [
    "src/uploaders/coupang_uploader.py",
    "src/uploaders/naver_uploader.py",
    "src/uploaders/elevenst_uploader.py",
    "src/seller_console/market_adapters/coupang_adapter.py",
    "src/seller_console/market_adapters/smartstore_adapter.py",
    "src/seller_console/market_adapters/eleven_adapter.py",
    "src/markets/adapters/naver_commerce_auth.py",
]

_DIRECT = re.compile(r"requests\.(get|post|put|patch|delete|request)\s*\(")


@pytest.mark.parametrize("path", _MARKET_OUTBOUND)
def test_no_direct_requests_in_market_outbound(path):
    """★ 관문 통일 — 마켓 아웃바운드는 relay_request 하나만 쓴다.

    누군가 새 호출을 requests로 직접 짜면 그 마켓만 조용히 직결로 나가 IP 차단에 걸린다.
    이번 스마트스토어 토큰이 정확히 그 사고였으므로 파일 단위로 못박는다.
    """
    src = Path(path).read_text(encoding="utf-8")
    hits = [ln.strip() for ln in src.splitlines() if _DIRECT.search(ln)]
    assert not hits, f"{path}에 직결 requests 호출 잔존: {hits}"


def test_ip_gated_markets_must_relay():
    """IP 게이트 마켓 목록에 쿠팡·스마트스토어·네이버가 빠지면 또 직결로 샌다."""
    assert {"coupang", "smartstore", "naver", "naver_commerce"} <= market_relay._IP_GATED_MARKETS


def test_non_gated_market_still_goes_direct(monkeypatch):
    """쇼피파이·우커머스·11번가는 같은 관문을 지나되 직결 — 릴레이 허용 호스트가 아니다(회귀 0)."""
    monkeypatch.setenv("MARKET_API_RELAY_URL", RELAY)
    seen = {}
    monkeypatch.setattr(requests, "request",
                        lambda method, url, **k: seen.update(url=url) or _Resp(200, {"ok": True}))
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("11번가가 릴레이로 갔다"))
    resp = market_relay.relay_request("GET", "https://api.11st.co.kr/rest/prodservices/product",
                                      market="elevenst")
    assert resp.status_code == 200
    assert seen["url"].startswith("https://api.11st.co.kr")
