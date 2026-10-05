"""Z3-B(오너 2026-10-05) — 타오바오 상세를 어디서 가져오나: `TAOBAO_DETAIL_PROVIDER` = mtop(기본) | onebound.

익명 mtop은 로그인 요구(IP 무관 — 오너 실측)라 보류. onebound면 외부 API(`taobao_provider_onebound`)로 —
이 설정만으로 담기 자동 경로가 켜진다(TAOBAO_MTOP_AUTO는 그대로 둠). 키가 비면 부팅 경고 + 「공급자 키 미설정」 실패
(조용한 mtop 폴백 없음). 실패는 (c) 수동 카드로 — mtop 재시도 안 함. mtop 코드는 지우지 않는다(Z3-L에서 재사용).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from src.collectors import taobao_provider_onebound as onebound

logger = logging.getLogger(__name__)


def provider() -> str:
    v = os.getenv("TAOBAO_DETAIL_PROVIDER", "mtop").strip().lower()
    return v if v in ("mtop", "onebound") else "mtop"


def status() -> Dict[str, Any]:
    miss = onebound.keys_missing()
    if miss:
        return {"state": "미설정", "line": "공급자 키 미설정 — " + " · ".join(miss)}
    return {"state": "ready", "line": "키 설정됨"}


def startup_check() -> str:
    if provider() != "onebound":
        return ""
    miss = onebound.keys_missing()
    if miss:
        msg = ("Z3-B 공급자: TAOBAO_DETAIL_PROVIDER=onebound인데 공급자 키 미설정(" + ", ".join(miss)
               + ") — mtop으로 돌리지 않고 그 건은 「공급자 키 미설정」 수동 카드로")
        logger.warning(msg)
        return msg
    msg = f"Z3-B 공급자: onebound · 일일 한도 {onebound.daily_cap()}회 · 단가 {onebound.UNIT_PRICE}"
    logger.info(msg)
    return msg


def fetch_detail(item_id: str, *, refresh: bool = False, transport=None) -> Dict[str, Any]:
    return onebound.fetch_detail(item_id, refresh=refresh, transport=transport)
