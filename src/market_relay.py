"""src/market_relay.py — 마켓 API 호출을 고정 IP 릴레이로 경유 (v8 P0, Phase 265).

쿠팡·네이버 OpenAPI는 호출 IP를 화이트리스트에 등록해야 한다. Render는 아웃바운드 IP가
고정이 아니라서 화이트리스트가 안 맞는다. → 서명까지 끝난 요청을 Bluehost 고정 IP 릴레이로
전달해 거기서 실제 호출(고정 IP)하고 결과만 돌려받는다.

- `MARKET_RELAY_URL` + `MARKET_RELAY_TOKEN` 둘 다 설정 + market이 릴레이 대상일 때만 경유.
  미설정이면 기존처럼 직접 호출(폴백 — 회귀 없음).
- Bearer 토큰 + HMAC(timestamp+body) 서명으로 인증/재전송 차단.
- 무상태: 릴레이는 자격증명/페이로드를 저장하지 않고 키도 로깅하지 않는다(릴레이 서버 책임).

서명은 호출 앱(여기)에서 이미 끝났고, 릴레이는 단순 포워딩만 한다(마켓별 로직 없음).
"""
from __future__ import annotations

import hashlib
import hmac
import json as _json
import logging
import os
import time

import base64
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ── v87-S6-2: mkt.php 릴레이(오너가 Bluehost 50.6.34.63에 설치) ──────────────────
#   프로토콜(오너 확정): POST {url, method, headers, body_b64} + 헤더 X-KGP-Relay-Key
#                        → {status, content_type, body_b64}
#   서명은 **호출부에서 원 URL 기준으로 이미 끝난다**(쿠팡 CEA는 path+query로 서명). 릴레이는
#   헤더·바디를 무가공 전달하므로 서명이 유효하다 — 여기서 URL을 바꾸거나 헤더를 만지면 안 된다.
_API_RELAY_ALLOWED_HOSTS = {"api-gateway.coupang.com", "api.commerce.naver.com"}


class RelayError(requests.exceptions.RequestException):
    """릴레이 경유 자체의 실패 — 마켓 직결 오류와 **구분해** 표기한다.

    requests 예외를 상속해 기존 호출부의 예외 처리 흐름을 타되, 메시지에 '릴레이 오류'를 달아
    마켓 카드에서 '쿠팡이 거부함'과 '우리 릴레이가 죽음'을 혼동하지 않게 한다.
    """


def api_relay_url() -> str:
    return (os.getenv("MARKET_API_RELAY_URL") or "").strip().rstrip("/")


def api_relay_enabled() -> bool:
    """MARKET_API_RELAY_URL이 있으면 전 마켓 요청을 릴레이 경유(없으면 현행 직결)."""
    return bool(api_relay_url())


def _api_relay_key() -> str:
    return (os.getenv("MARKET_API_RELAY_KEY") or os.getenv("MARKET_RELAY_TOKEN") or "").strip()


def assert_host_allowed(url: str) -> str:
    """허용 외 호스트는 **클라이언트 단에서도** 거부(릴레이 검증에만 기대지 않는다)."""
    host = (urlparse(url).hostname or "").lower()
    if host not in _API_RELAY_ALLOWED_HOSTS:
        raise RelayError(f"릴레이 오류: 허용되지 않은 호스트({host or 'unknown'})")
    return host


def _body_bytes(json_body, data) -> bytes:
    if json_body is not None:
        return _json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    if data is None:
        return b""
    return data.encode("utf-8") if isinstance(data, str) else (
        data if isinstance(data, (bytes, bytearray)) else _json.dumps(data, ensure_ascii=False).encode("utf-8")
    )


def _api_relay_send(method, url, headers, json_body, data, timeout):
    """mkt.php 경유 1회 전송. 릴레이 계층 실패는 RelayError로 올린다."""
    payload = {
        "url": url,                                   # 원 URL 그대로(서명 대상과 동일해야 한다)
        "method": str(method).upper(),
        "headers": dict(headers or {}),
        "body_b64": base64.b64encode(_body_bytes(json_body, data)).decode("ascii"),
    }
    try:
        r = requests.post(
            api_relay_url(),
            json=payload,
            headers={"X-KGP-Relay-Key": _api_relay_key(), "Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise RelayError(f"릴레이 오류: 릴레이에 닿지 못했습니다 ({exc})") from exc
    if r.status_code != 200:
        raise RelayError(f"릴레이 오류: 릴레이가 HTTP {r.status_code}")
    try:
        out = r.json()
    except ValueError as exc:
        raise RelayError("릴레이 오류: 릴레이 응답이 JSON이 아닙니다") from exc
    if out.get("error"):
        raise RelayError(f"릴레이 오류: {out.get('error')}")
    if "status" not in out:
        raise RelayError("릴레이 오류: 응답에 status가 없습니다")
    try:
        body = base64.b64decode(out.get("body_b64") or "").decode("utf-8", "replace")
    except Exception as exc:                                   # noqa: BLE001 — 형식 위반은 릴레이 문제
        raise RelayError("릴레이 오류: body_b64를 해석하지 못했습니다") from exc
    return RelayResponse(int(out["status"]), body,
                         headers={"Content-Type": out.get("content_type") or ""})


def _relay_markets() -> set:
    raw = os.getenv("MARKET_RELAY_MARKETS") or "coupang,smartstore,naver"
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def relay_enabled(market: str = "") -> bool:
    """릴레이 경유 조건: URL+TOKEN 설정 + market이 대상."""
    if not (os.getenv("MARKET_RELAY_URL") and os.getenv("MARKET_RELAY_TOKEN")):
        return False
    m = (market or "").strip().lower()
    return (not m) or (m in _relay_markets())


class RelayResponse:
    """requests.Response 호환 최소 shim (status_code/json()/text/raise_for_status)."""

    def __init__(self, status_code: int, text: str = "", headers=None):
        self.status_code = int(status_code)
        self.text = text or ""
        self.headers = headers or {}

    def json(self):
        return _json.loads(self.text) if self.text else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} via relay", response=self)


def relay_request(method, url, *, headers=None, json=None, data=None, timeout=30, market="", key=""):
    """릴레이 설정 시 고정 IP 경유, 아니면 직접 requests 호출(폴백).

    v45: 모든 마켓 호출은 market_throttle을 타 페이싱(마켓별 초당 한도) + 429/5xx 지수
    백오프 재시도(최대 3회)한다. key=자격 단위(vendorId/앱ID; 없으면 마켓 전역).

    Returns: requests.Response 또는 RelayResponse(호환).
    """
    from src.market_throttle import throttled_request

    # v87-S6-2: 허용 호스트 검증은 **스로틀/재시도 바깥**에서 — 설정 오류를 3회 재시도해봐야 소용없다.
    if api_relay_enabled():
        assert_host_allowed(url)

    def _send():
        # mkt.php 릴레이가 설정돼 있으면 전 요청을 경유(구 MARKET_RELAY_URL 경로보다 우선).
        if api_relay_enabled():
            return _api_relay_send(method, url, headers, json, data, 35)
        if not relay_enabled(market):
            return requests.request(method, url, headers=headers, json=json, data=data, timeout=timeout)
        relay_url = os.getenv("MARKET_RELAY_URL", "").rstrip("/")
        token = os.getenv("MARKET_RELAY_TOKEN", "")
        body = None
        if json is not None:
            body = _json.dumps(json, ensure_ascii=False)
        elif data is not None:
            body = data if isinstance(data, str) else _json.dumps(data, ensure_ascii=False)
        spec = {"method": str(method).upper(), "url": url, "headers": dict(headers or {}), "body": body}
        payload = _json.dumps(spec, ensure_ascii=False)
        ts = str(int(time.time()))
        sig = hmac.new(token.encode(), (ts + payload).encode(), hashlib.sha256).hexdigest()
        r = requests.post(
            relay_url + "/relay",
            data=payload.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "X-Relay-Timestamp": ts,
                "X-Relay-Signature": sig,
                "Content-Type": "application/json",
            },
            timeout=timeout + 10,
        )
        r.raise_for_status()
        out = r.json()
        return RelayResponse(int(out.get("status", 502)), out.get("body", ""), headers=out.get("headers"))

    return throttled_request(_send, market=(market or "").strip().lower() or "generic", key=key or "")
