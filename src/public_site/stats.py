"""L1 랜딩 숫자 3개 — **DB 실측만**(가짜 숫자 금지). 0이면 0, 못 읽으면 None(화면은 「—」).

- 누적 수집 건수: collect_history(삭제 안 된 행, 전체 셀러)
- 등록 성공 건수: market_registrations(마켓이 등록을 받아 준 행 — 나중에 반려된 것은 뺀다)
- 연동 마켓 수: market_links(셀러가 키를 연결해 둔 마켓 종류, 계정 접미사는 한 마켓으로)
공개 페이지라 5분 캐시(방문마다 DB를 치지 않는다).
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)
_TTL = 300
_cache: Dict[str, object] = {"at": 0.0, "val": None}


def _collected() -> Optional[int]:
    from src.db.pg import pg_enabled
    if pg_enabled():
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT count(*) FROM collect_history WHERE deleted_at IS NULL")
            return int(cur.fetchone()[0])
    from src.seller_console import collect_history_store as S
    return sum(1 for r in S._in_memory if not r.get("deleted_at"))


def _registered() -> Optional[int]:
    from src.db import market_registrations_pg as R
    if R.enabled():
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT count(*) FROM market_registrations WHERE deleted_at IS NULL AND status <> 'rejected'")
            return int(cur.fetchone()[0])
    return sum(1 for r in R._MEM.values() if r.get("status") != "rejected")


def _markets() -> Optional[int]:
    from src.db.pg import pg_enabled
    if not pg_enabled():
        return None                                   # 파일 저장소(개발)는 셀러 전체를 세지 않는다 — 모름
    from src.db import pg
    with pg.query() as cur:
        cur.execute("SELECT DISTINCT market FROM market_links WHERE deleted_at IS NULL")
        rows = [str(r[0] or "") for r in cur.fetchall()]
    return len({m.split("_")[0] for m in rows if m})


def live(now: Optional[float] = None) -> Dict[str, Optional[int]]:
    now = now or time.time()
    if _cache["val"] is not None and now - float(_cache["at"]) < _TTL:
        return dict(_cache["val"])                    # type: ignore[arg-type]
    out: Dict[str, Optional[int]] = {}
    for key, fn in (("collected", _collected), ("registered", _registered), ("markets", _markets)):
        try:
            out[key] = fn()
        except Exception as exc:                      # noqa: BLE001 — 못 읽으면 「—」(0으로 꾸미지 않음)
            logger.warning("[공개 랜딩] %s 집계 실패: %s", key, exc)
            out[key] = None
    _cache.update(at=now, val=dict(out))
    return out


def reset() -> None:
    _cache.update(at=0.0, val=None)
