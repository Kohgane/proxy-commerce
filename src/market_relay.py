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
from urllib.parse import urlencode, urlparse

import requests

logger = logging.getLogger(__name__)

# ── v87-S6-2: mkt.php 릴레이(오너가 Bluehost 50.6.34.63에 설치) ──────────────────
#   프로토콜(오너 확정): POST {url, method, headers, body_b64} + 헤더 X-KGP-Relay-Key
#                        → {status, content_type, body_b64}
#   서명은 **호출부에서 원 URL 기준으로 이미 끝난다**(쿠팡 CEA는 path+query로 서명). 릴레이는
#   헤더·바디를 무가공 전달하므로 서명이 유효하다 — 여기서 URL을 바꾸거나 헤더를 만지면 안 된다.
_API_RELAY_ALLOWED_HOSTS = {"api-gateway.coupang.com", "api.commerce.naver.com"}

# IP 화이트리스트가 걸린 마켓 — 이 마켓의 요청은 **토큰 발급까지 포함해** 반드시 릴레이를 타야 한다.
#   v87-S7 실측: 쿠팡은 릴레이로 그린이었는데 스마트스토어만 GW.IP_NOT_ALLOWED였다. 원인은 상품 API가
#   아니라 **OAuth 토큰 발급이 직결로 나가서** — 토큰을 못 받으니 그 뒤가 전부 막힌 것.
_IP_GATED_MARKETS = {"coupang", "smartstore", "naver", "naver_commerce"}

# v87-S8: 릴레이 호출용 UA. 기본값 `python-requests/…`는 Bluehost mod_security가 406으로 끊는다.
#   봇 UA로 위장하지 않고 우리 서비스를 밝히는 문자열을 쓴다(차단 규칙 회피가 아니라 정상 식별).
_RELAY_USER_AGENT = "gogabridj-relay/1.0 (+https://kohganepercentiii.com)"


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


def ip_gated(market: str) -> bool:
    """이 마켓이 **IP 화이트리스트 게이트**라 릴레이를 타야 하는가.

    화면(마켓 연동)이 "허용 목록에 등록할 IP"를 안내할 때 이 판정으로 갈린다. 게이트 마켓이면
    릴레이 고정 IP, 아니면 우리 서버 아웃바운드 IP다 — **판정을 화면에서 다시 쓰면 갈라진다.**
    """
    return (market or "").strip().lower() in _IP_GATED_MARKETS


_RELAY_IP_CACHE = {"ip": None}


def relay_outbound_ip() -> str:
    """릴레이가 마켓에 대고 나가는 **고정 IP**. 하드코딩하지 않고 릴레이 설정에서 파생한다.

    ★ 지뢰(오너 2026-09-02): 게이트 마켓 안내에 **Render 아웃바운드 IP를 적으면 안 된다.**
      Render는 공유 대역이고 값이 바뀐다 — 오너가 그 IP를 마켓 허용 목록에 등록하고 며칠 뒤
      다시 막히는 재발 경로다. 게이트 마켓의 실제 발신자는 릴레이 서버 하나뿐이다.

    파생 순서: `MARKET_RELAY_IP`(명시) → 릴레이 URL 호스트가 IP 리터럴이면 그 값 → DNS 해석.
    셋 다 안 되면 **빈 문자열**을 돌려주고 화면이 "릴레이 IP 미확인"이라고 말한다(추측 금지).
    """
    explicit = (os.getenv("MARKET_RELAY_IP") or "").strip()
    if explicit:
        return explicit
    if _RELAY_IP_CACHE["ip"] is not None:
        return _RELAY_IP_CACHE["ip"]
    host = ""
    for u in (api_relay_url(), (os.getenv("MARKET_RELAY_URL") or "").strip()):
        if u:
            host = (urlparse(u).hostname or "").strip()
            if host:
                break
    ip = ""
    if host:
        try:
            import ipaddress
            ipaddress.ip_address(host)
            ip = host                                  # 이미 IP 리터럴
        except ValueError:
            try:
                import socket
                ip = socket.gethostbyname(host)
            except Exception:
                ip = ""
    _RELAY_IP_CACHE["ip"] = ip
    return ip


def assert_host_allowed(url: str) -> str:
    """허용 외 호스트는 **클라이언트 단에서도** 거부(릴레이 검증에만 기대지 않는다)."""
    host = (urlparse(url).hostname or "").lower()
    if host not in _API_RELAY_ALLOWED_HOSTS:
        raise RelayError(f"릴레이 오류: 허용되지 않은 호스트({host or 'unknown'})")
    return host


def _body_bytes(json_body, data) -> bytes:
    """요청 바디를 바이트로. **requests와 같은 규칙으로 인코딩해야 한다.**

    v87-S7 함정: 네이버 OAuth 토큰 발급은 `data={...}` 폼 전송이다. requests는 dict data를
    x-www-form-urlencoded로 보내는데, 여기서 JSON으로 바꿔 보내면 릴레이 너머에서 네이버가
    폼을 못 읽어 토큰 발급이 조용히 실패한다(직결일 땐 되던 게 릴레이만 켜면 깨짐).
    """
    if json_body is not None:
        return _json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    return urlencode(data, doseq=True).encode("utf-8")      # dict → 폼 인코딩(requests 동일)


def _content_type_for(json_body, data, headers) -> str:
    """requests가 자동으로 붙여주던 Content-Type을 명시한다(릴레이는 헤더를 그대로 넘기므로)."""
    for k in (headers or {}):
        if k.lower() == "content-type":
            return ""                                        # 호출부가 이미 지정했으면 존중
    if json_body is not None:
        return "application/json"
    if isinstance(data, dict):
        return "application/x-www-form-urlencoded"
    return ""


def _api_relay_send(method, url, headers, json_body, data, timeout):
    """mkt.php 경유 1회 전송. 릴레이 계층 실패는 RelayError로 올린다."""
    hdrs = dict(headers or {})
    ct = _content_type_for(json_body, data, hdrs)
    if ct:
        hdrs["Content-Type"] = ct
    payload = {
        "url": url,                                   # 원 URL 그대로(서명 대상과 동일해야 한다)
        "method": str(method).upper(),
        "headers": hdrs,
        "body_b64": base64.b64encode(_body_bytes(json_body, data)).decode("ascii"),
    }
    try:
        r = requests.post(
            api_relay_url(),
            json=payload,
            # v87-S8: **릴레이 봉투 헤더에만** UA·Accept를 명시한다(마켓 원 요청 헤더는 payload 안에
            #   무가공 유지 — 서명 불변). requests 기본 UA(`python-requests/x.y.z`)는 Bluehost의
            #   Apache mod_security가 406 'Not Acceptable'로 끊는다(실측: 같은 요청에 UA만 브라우저로
            #   바꾸면 406이 사라지고 스크립트까지 도달). 이 프로젝트엔 같은 선례가 있다 —
            #   WooCommerce 406도 원인이 UA/Accept 누락이었다.
            headers={
                "X-KGP-Relay-Key": _api_relay_key(),
                "Content-Type": "application/json",
                "User-Agent": _RELAY_USER_AGENT,
                "Accept": "application/json",
            },
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


def relay_request(method, url, *, headers=None, json=None, data=None, params=None, timeout=30, market="", key=""):
    """릴레이 설정 시 고정 IP 경유, 아니면 직접 requests 호출(폴백).

    v45: 모든 마켓 호출은 market_throttle을 타 페이싱(마켓별 초당 한도) + 429/5xx 지수
    백오프 재시도(최대 3회)한다. key=자격 단위(vendorId/앱ID; 없으면 마켓 전역).

    Returns: requests.Response 또는 RelayResponse(호환).
    """
    from src.market_throttle import throttled_request

    # v87-S7: 릴레이는 URL 하나만 받으므로 params를 URL에 합쳐 보낸다(직결은 requests에 그대로 넘긴다).
    #   ※ 쿠팡 CEA 서명은 path+query 기준이므로, 서명한 쪽과 실제 URL이 어긋나지 않게 호출부가
    #     서명 대상에 쿼리를 포함했는지 확인해야 한다(이 함수는 URL을 바꾸지 않고 합치기만 한다).
    if params:
        _q = urlencode(params, doseq=True)
        url = url + ("&" if "?" in url else "?") + _q
        params = None

    # v87-S6-2: 허용 호스트 검증은 **스로틀/재시도 바깥**에서 — 설정 오류를 3회 재시도해봐야 소용없다.
    # v87-S7: 이 함수가 **모든 마켓 아웃바운드의 단일 관문**이다. IP 화이트리스트가 걸린 마켓
    #   (쿠팡·스마트스토어/네이버)은 반드시 릴레이를 타야 하고, 그 외 마켓(쇼피파이·우커머스·11번가)은
    #   같은 관문을 지나되 직결로 나간다 — 릴레이 허용 호스트가 아니기 때문이다.
    _via_relay = False
    if api_relay_enabled():
        if (market or "").strip().lower() in _IP_GATED_MARKETS:
            assert_host_allowed(url)          # IP 게이트 마켓이 엉뚱한 호스트로 나가면 즉시 거부
            _via_relay = True
        else:
            _via_relay = (urlparse(url).hostname or "").lower() in _API_RELAY_ALLOWED_HOSTS

    def _send():
        # mkt.php 릴레이가 설정돼 있으면 경유(구 MARKET_RELAY_URL 경로보다 우선).
        if _via_relay:
            return _api_relay_send(method, url, headers, json, data, 35)
        if not relay_enabled(market):
            # 직결도 관문을 지난 뒤 **한 가지 방식**(requests.request)으로 나간다.
            #   v87-S7: 호출부를 이 관문으로 옮기면 그 모듈의 테스트도 requests.request를 목해야 한다
            #   (동사별 함수로 분기하면 반대로 쿠팡 쪽 기존 목이 빗나간다 — 실측으로 확인).
            _kw = {"headers": headers, "timeout": timeout}
            if json is not None:
                _kw["json"] = json
            if data is not None:
                _kw["data"] = data
            if params is not None:
                _kw["params"] = params
            return requests.request(method, url, **_kw)
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
