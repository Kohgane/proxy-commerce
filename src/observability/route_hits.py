"""src/observability/route_hits.py — 화면 방문 카운터 (오너 부수 승인, 2026-09-03).

**왜:** 확산 순서를 "구조적 노출도"로 추정했는데(핵심 내비·대시보드 링크·작업 동선),
그건 트래픽이 아니다. 어느 화면을 실제로 자주 여는지 알면 6-e 이후 순서를 사실로 정한다.
훗날 연동대행사 운영 지표의 씨앗이기도 하다.

**규율 (오너 계약):**
- **로그 기반 카운트만.** 별도 저장소·스키마 없음. 프로세스 메모리에 세고 주기적으로 1줄 찍는다.
- **PII 0.** 세는 건 **Flask 엔드포인트 이름**이지 URL이 아니다 — 쿼리스트링·경로 파라미터
  (상품 id·셀러 id)는 애초에 들어오지 않는다. 사용자·세션 식별자도 안 센다.
- **화면 없음.** 대시보드를 만들지 않는다. 주간 집계 텍스트 한 줄이면 충분하다.
- 카운터가 요청을 죽이지 않는다(예외는 삼키고 지나간다).

한계(정직): 프로세스 메모리라 **워커별로 따로 세고 재시작하면 0**이다. 절대값이 아니라
**화면 사이 비율**을 보는 용도다. 워커가 여럿이면 로그 줄도 여럿 나오고, 합치면 전체다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import Counter

logger = logging.getLogger(__name__)

# 집계 주기(초). 기본 6시간 — "주간 집계"를 쓰려면 로그를 모으면 된다.
FLUSH_EVERY_SEC = int(os.getenv("ROUTE_HITS_FLUSH_SEC") or 21600)
TOP_N = int(os.getenv("ROUTE_HITS_TOP_N") or 25)
# 재배포가 잦으면 6시간을 못 채우고 프로세스가 죽어 집계가 통째로 사라진다.
# 건수가 차도 한 번 찍어 그 손실을 줄인다(둘 중 먼저 오는 쪽).
FLUSH_EVERY_HITS = int(os.getenv("ROUTE_HITS_FLUSH_HITS") or 2000)

_lock = threading.Lock()
_hits: Counter = Counter()
_since = time.time()


def enabled() -> bool:
    """기본 켜짐. `ROUTE_HITS=0`이면 완전히 끈다(카운트도 안 한다)."""
    return (os.getenv("ROUTE_HITS") or "1").strip().lower() not in ("0", "false", "off", "")


def record(endpoint: str) -> None:
    """엔드포인트 이름 하나를 센다. **URL도 파라미터도 받지 않는다**(PII 유입 경로 차단)."""
    name = (endpoint or "").strip()
    if not name:
        return
    with _lock:
        _hits[name] += 1


def snapshot() -> dict:
    with _lock:
        return dict(_hits)


def reset() -> None:
    global _since
    with _lock:
        _hits.clear()
        _since = time.time()


def _format(counts: dict, window_sec: float) -> str:
    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]
    body = " ".join(f"{name}={n}" for name, n in top)
    return (f"화면 방문 집계 window_h={window_sec / 3600:.1f} total={total} "
            f"routes={len(counts)} {body}")


def maybe_flush(now: float = None) -> str:
    """주기가 됐으면 1줄 찍고 비운다. 찍은 줄을 반환(안 찍었으면 빈 문자열)."""
    now = now if now is not None else time.time()
    with _lock:
        if not _hits:
            return ""
        if (now - _since) < FLUSH_EVERY_SEC and sum(_hits.values()) < FLUSH_EVERY_HITS:
            return ""
        counts, window = dict(_hits), now - _since
        _hits.clear()
    globals()["_since"] = now
    line = _format(counts, window)
    logger.info("%s", line)
    return line


def install(app) -> None:
    """`after_request`에 붙인다. 카운터가 요청을 죽이지 않게 전부 삼킨다."""
    if not enabled():
        return

    @app.after_request
    def _count_route_hit(response):                     # noqa: ANN001 — Flask 훅
        try:
            from flask import request
            # 화면(=HTML GET)만 센다. API·정적·헬스체크는 '어느 화면을 자주 보나'와 무관하다.
            if request.method == "GET" and (response.content_type or "").startswith("text/html"):
                record(request.endpoint or "")
            maybe_flush()
        except Exception:                               # noqa: BLE001 — 계측이 요청을 죽이지 않는다
            pass
        return response
