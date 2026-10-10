"""Y7-G(오너 2026-10-09) — 네이버 CDN 업로드 결과 캐시. 사전검증이 올린 장을 등록이 **다시 올리지 않게**.

키 = 계정(스토어) + 정규화한 원본 URL. 값 = 네이버가 준 CDN URL(shop-phinf). 저장소는 잡 상태와 같은 `app_state`
(워커가 둘이라 프로세스 메모리로는 사전검증 워커와 등록 워커가 갈린다). PG가 꺼져 있으면 같은 모듈의 메모리 폴백.
성공만 저장한다 — 실패는 등록 때 다시 시도한다(그 사이 원인이 풀렸을 수 있다).
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PREFIX = "naver_cdn:"


def _ttl_days() -> int:
    try:
        return max(1, int(os.getenv("NAVER_CDN_CACHE_DAYS", "30") or 30))
    except (TypeError, ValueError):
        return 30


def _key(account: str, url: str) -> str:
    h = hashlib.sha1(str(url or "").encode("utf-8")).hexdigest()[:24]
    return f"{PREFIX}{(account or '_default').lower()}:{h}"


def _store():
    from src.db import image_translate_queue_pg as st
    return st


def get(account: str, url: str) -> str:
    """캐시된 CDN URL — 없거나 만료·원본 불일치면 ''. 조회 실패는 캐시 없음으로(등록을 막지 않는다)."""
    try:
        v = _store().state_get(_key(account, url)) or {}
    except Exception as exc:                      # noqa: BLE001
        logger.info("[네이버 CDN 캐시] 조회 실패(없는 것으로): %s", exc)
        return ""
    if not v or str(v.get("src") or "") != str(url or "") or not v.get("url"):
        return ""
    try:
        at = datetime.fromisoformat(str(v.get("at")))
        if datetime.now(timezone.utc) - at > timedelta(days=_ttl_days()):
            return ""
    except (TypeError, ValueError):
        return ""
    return str(v["url"])


def put(account: str, url: str, cdn_url: str) -> None:
    try:
        _store().state_set(_key(account, url), {"src": str(url), "url": str(cdn_url),
                                                "at": datetime.now(timezone.utc).isoformat()})
    except Exception as exc:                      # noqa: BLE001
        logger.info("[네이버 CDN 캐시] 저장 실패(다음에 다시 올림): %s", exc)


FAIL_PREFIX = "naver_cdn_fail:"


def put_fail(account: str, url: str, reason: str) -> None:
    """Y7-J(오너 2026-10-10) — 못 올린 장의 **사유**를 남긴다(캐시로 쓰지 않음 — 다음에 다시 시도한다).
    실측: 13802276439 상세 1장(`…_1200x1200q30.jpg_.webp`)이 캐시에 없었는데 사유는 Render 로그에만 있어 읽지 못했다."""
    try:
        _store().state_set(_key(account, url).replace(PREFIX, FAIL_PREFIX, 1),
                           {"src": str(url), "reason": str(reason or "")[:300],
                            "at": datetime.now(timezone.utc).isoformat()})
    except Exception as exc:                      # noqa: BLE001
        logger.info("[네이버 CDN 캐시] 실패 사유 저장 실패: %s", exc)


def get_fail(account: str, url: str) -> dict:
    try:
        return _store().state_get(_key(account, url).replace(PREFIX, FAIL_PREFIX, 1)) or {}
    except Exception:                             # noqa: BLE001
        return {}
