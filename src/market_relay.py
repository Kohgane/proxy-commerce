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

import requests

logger = logging.getLogger(__name__)


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

    def _send():
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
