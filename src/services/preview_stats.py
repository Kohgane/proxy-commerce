"""src/services/preview_stats.py — J4(오너 2026-09-30-J): 쿠팡 미리보기 「예상 모습」 발생률.

카테고리 메타를 못 받아 「예상 모습」으로 보여 준 횟수를 **시간 단위 칸**에 센다(`app_state` `cp_preview:h:<UTC 시각>`).
24시간 비율이 10%를 넘으면 메타 캐시(카테고리별 24h)를 넣는다 — 그 판단의 근거가 이 숫자다.
사유는 예외 종류·코드만 적는다(키·주소·본문 안 적음).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_PREFIX = "cp_preview:h:"
THRESHOLD = 0.10


def _key(now) -> str:
    return _PREFIX + now.astimezone(timezone.utc).strftime("%Y%m%d%H")


def record(estimated: bool, reason: str = "", now=None) -> None:
    from src.db import image_translate_queue_pg as st
    now = now or datetime.now(timezone.utc)
    k = _key(now)
    try:
        with _LOCK:
            v = st.state_get(k)
            v["total"] = int(v.get("total") or 0) + 1
            if estimated:
                v["estimated"] = int(v.get("estimated") or 0) + 1
                rs = dict(v.get("reasons") or {})
                r = (reason or "사유 없음")[:60]
                rs[r] = int(rs.get(r) or 0) + 1
                v["reasons"] = rs
            st.state_set(k, v)
    except Exception as exc:                  # 세는 게 실패해도 미리보기는 막지 않는다
        logger.warning("[쿠팡 미리보기] 카운트 실패: %s", exc)
    if estimated:
        logger.info("[쿠팡 미리보기] 예상 모습 — 사유 %s", reason or "사유 없음")


def window(hours: int = 24, now=None) -> dict:
    from src.db import image_translate_queue_pg as st
    now = now or datetime.now(timezone.utc)
    total = est = 0
    reasons: dict = {}
    for h in range(int(hours)):
        v = st.state_get(_key(now - timedelta(hours=h)))
        total += int(v.get("total") or 0)
        est += int(v.get("estimated") or 0)
        for r, n in (v.get("reasons") or {}).items():
            reasons[r] = reasons.get(r, 0) + int(n)
    ratio = round(est / total, 3) if total else None
    return {"hours": int(hours), "total": total, "estimated": est, "ratio": ratio, "threshold": THRESHOLD,
            "over": bool(ratio is not None and ratio > THRESHOLD),
            "reasons": dict(sorted(reasons.items(), key=lambda x: -x[1]))}
