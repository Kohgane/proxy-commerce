"""src/market_throttle.py — 마켓 API 호출 스로틀 큐(아웃바운드 레이트리밋 준수).

오너 스펙:
- 모든 마켓 API 호출은 직접 호출 금지 → 이 스로틀을 타게 한다(페이싱).
- 마켓별 초당 한도(안전마진): 네이버=앱ID당 2/s→**1.5**, 쿠팡=vendorId당 10/s→**7**. 마켓별 설정값.
- 429/5xx → 지수 백오프(1s→2s→4s) 재시도 **최대 3회**. 최종 실패는 실패로 응답(가짜 성공 금지).
- 응답 헤더의 잔여량(GNCP-GW-RateLimit-Remaining 등) 로깅.

키(market, key)별 토큰버킷으로 프로세스 내 페이싱을 직렬화한다. key는 vendorId/앱ID/셀러 등
자격 단위(없으면 마켓 전역). 벌크(일괄 등록·수집)는 전부 이 스로틀을 타 429를 원천 방지한다.
"""
from __future__ import annotations

import collections
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# 마켓별 초당 허용(안전마진 적용). env MARKET_RPS_<MARKET>로 오버라이드.
_MARKET_RPS = {
    "naver": 1.5, "smartstore": 1.5,
    "coupang": 7.0,
    "elevenst": 3.0, "woocommerce": 5.0, "shopify": 4.0,
}
_RETRYABLE = {429, 500, 502, 503, 504}
_REMAINING_HEADERS = (
    "GNCP-GW-RateLimit-Remaining", "X-RateLimit-Remaining",
    "x-ratelimit-remaining", "RateLimit-Remaining", "X-Rate-Limit-Remaining",
)

_lock = threading.Lock()
_next_at: dict = {}   # (market,key) -> 다음 호출 가능 시각(monotonic)
_stats: dict = collections.defaultdict(lambda: {"calls": 0, "retries": 0, "429": 0, "5xx": 0})


def _default_rps():
    try:
        return float(os.getenv("MARKET_DEFAULT_RPS", "3") or 3)
    except (TypeError, ValueError):
        return 3.0


def rps_for(market: str) -> float:
    """마켓별 초당 허용(안전마진). env MARKET_RPS_<MARKET> 우선."""
    m = (market or "").strip().lower()
    ov = os.getenv(f"MARKET_RPS_{m.upper()}")
    if ov:
        try:
            return float(ov)
        except ValueError:
            pass
    return _MARKET_RPS.get(m, _default_rps())


def _acquire(market: str, key: str):
    """토큰버킷 페이싱 — (market,key)별 최소 간격(1/RPS)을 보장. sleep은 락 밖."""
    rps = rps_for(market)
    interval = (1.0 / rps) if rps > 0 else 0.0
    k = (market, key)
    with _lock:
        now = time.monotonic()
        nxt = _next_at.get(k, 0.0)
        wait = max(0.0, nxt - now)
        _next_at[k] = max(now, nxt) + interval
    if wait > 0:
        time.sleep(wait)


def _log_remaining(market: str, resp):
    try:
        h = getattr(resp, "headers", None) or {}
        for name in _REMAINING_HEADERS:
            if name in h:
                logger.info("마켓 %s 잔여 호출: %s=%s", market, name, h[name])
                return
    except Exception:
        pass


def throttled_request(do_request, *, market: str, key: str = "", retries: int = 3, base_delay: float = 1.0):
    """마켓 HTTP 호출을 페이싱 + 429/5xx 지수 백오프 재시도로 감싼다.

    Args:
        do_request: 실제 HTTP 호출 콜러블 — status_code/.headers 있는 응답 반환.
        market: 마켓 코드(레이트리밋 선택). key: 자격 단위(vendorId/앱ID; 없으면 마켓 전역).
        retries: 최대 재시도 횟수(기본 3 → 총 4회 시도). base_delay: 첫 백오프(1s→2s→4s).
    Returns:
        마지막 응답(성공이면 성공 응답, 재시도 소진이면 마지막 실패 응답 그대로 — 가짜 성공 0).
        do_request가 예외를 던지면 재시도 후 최종 예외 전파.
    """
    sk = (market, key or "*")
    last = None
    for attempt in range(retries + 1):
        _acquire(market, key)
        _stats[sk]["calls"] += 1
        try:
            resp = do_request()
        except Exception as exc:   # noqa: BLE001 — 네트워크 오류도 재시도 대상
            last = exc
            if attempt < retries:
                _stats[sk]["retries"] += 1
                logger.warning("마켓 %s 재시도 %d/%d (예외: %s)", market, attempt + 1, retries, exc)
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
        code = int(getattr(resp, "status_code", 200) or 200)
        _log_remaining(market, resp)
        if code in _RETRYABLE:
            _stats[sk]["429" if code == 429 else "5xx"] += 1
            last = resp
            if attempt < retries:
                _stats[sk]["retries"] += 1
                logger.warning("마켓 %s 재시도 %d/%d (HTTP %s)", market, attempt + 1, retries, code)
                time.sleep(base_delay * (2 ** attempt))   # 1s → 2s → 4s
                continue
            logger.warning("마켓 %s 재시도 %d회 소진 — 최종 실패(HTTP %s)", market, retries, code)
            return resp
        return resp
    return last


def pace(market: str, key: str = ""):
    """페이싱만 필요한 호출자용(자체 429 재시도가 이미 있는 woo/shopify 등) — 큐 간격만 적용."""
    _acquire((market or "").strip().lower() or "generic", key or "")
    _stats[((market or "generic"), key or "*")]["calls"] += 1


def get_stats() -> dict:
    """진단용 — (market,key)별 호출/재시도/429/5xx 누적."""
    return {f"{m}:{k}": dict(v) for (m, k), v in _stats.items()}


def reset_stats():
    _stats.clear()
    _next_at.clear()
