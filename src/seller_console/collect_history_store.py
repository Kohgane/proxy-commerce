"""src/seller_console/collect_history_store.py — 수집 이력 저장소 (Phase 135.2).

Sheets `collect_history` 워크시트 자동 부트스트랩.
컬럼: id | collected_at | source | domain | url | title | image_url | price | currency | status | preview_url | extra_json
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "collect_history"
_HEADERS = [
    "id", "collected_at", "source", "domain", "url", "title",
    "image_url", "price", "currency", "status", "preview_url", "extra_json",
]

# 인메모리 폴백 저장소 (GOOGLE_SHEET_ID 없을 때)
_in_memory: list[dict] = []


def _get_worksheet():
    from src.utils.sheets import open_sheet
    return open_sheet(_SHEET_ID, _WS_NAME)


def _ensure_headers(ws) -> None:
    try:
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != "id":
            ws.insert_row(_HEADERS, index=1)
    except Exception:
        pass


def append(
    *,
    source: str,
    url: str,
    title: str,
    image: str = "",
    price: str = "",
    currency: str = "",
    status: str = "ok",
    preview_url: str = "",
    extra: dict = None,
) -> str:
    """수집 이력 1건 추가.

    Returns:
        생성된 item_id (6바이트 hex)
    """
    item_id = secrets.token_hex(6)
    domain = urlparse(url).netloc
    now = datetime.now(timezone.utc).isoformat()
    row_data = {
        "id": item_id,
        "collected_at": now,
        "source": source,
        "domain": domain,
        "url": url,
        "title": title,
        "image_url": image or "",
        "price": str(price or ""),
        "currency": currency or "",
        "status": status,
        "preview_url": preview_url or f"/seller/collect/preview/{item_id}",
        "extra_json": json.dumps(extra or {}, ensure_ascii=False),
    }

    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            _ensure_headers(ws)
            ws.append_row([row_data[h] for h in _HEADERS])
            logger.info("수집 이력 저장: id=%s source=%s domain=%s", item_id, source, domain)
        except Exception as exc:
            logger.warning("수집 이력 Sheets 저장 실패: %s", exc)
            _in_memory.append(row_data)
    else:
        _in_memory.append(row_data)

    return item_id


def list_items(*, domain: str = "", source: str = "", days: int = 30) -> list[dict]:
    """수집 이력 목록 반환 (최신순).

    Args:
        domain: 도메인 필터 (빈 문자열 = 전체)
        source: 소스 필터 (extension/bookmarklet/manual/bulk, 빈 문자열 = 전체)
        days: 최근 N일
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows: list[dict] = []

    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            records = ws.get_all_records()
            rows = records
        except Exception as exc:
            logger.warning("수집 이력 조회 실패: %s", exc)
            rows = list(_in_memory)
    else:
        rows = list(_in_memory)

    result = []
    for row in rows:
        if row.get("collected_at", "") < cutoff:
            continue
        if domain and row.get("domain", "") != domain:
            continue
        if source and row.get("source", "") != source:
            continue
        result.append(dict(row))

    result.sort(key=lambda r: r.get("collected_at", ""), reverse=True)
    return result


def get(item_id: str) -> Optional[dict]:
    """ID로 단건 조회."""
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            records = ws.get_all_records()
            for row in records:
                if row.get("id") == item_id:
                    return dict(row)
        except Exception as exc:
            logger.warning("수집 이력 단건 조회 실패: %s", exc)
    # 인메모리 폴백
    for row in _in_memory:
        if row.get("id") == item_id:
            return dict(row)
    return None


def summary(days: int = 30) -> dict:
    """기간별 요약 통계."""
    items = list_items(days=days)
    by_source: dict[str, int] = {
        "extension": 0,
        "bookmarklet": 0,
        "manual": 0,
        "bulk": 0,
    }
    today_prefix = datetime.now(timezone.utc).date().isoformat()
    today_count = 0
    domain_set: set[str] = set()

    for item in items:
        src = item.get("source", "")
        # normalize source keys
        if src in ("chrome_extension", "extension"):
            by_source["extension"] += 1
        elif src == "bookmarklet":
            by_source["bookmarklet"] += 1
        elif src == "manual":
            by_source["manual"] += 1
        elif src in ("bulk", "bulk_collect"):
            by_source["bulk"] += 1
        if item.get("collected_at", "").startswith(today_prefix):
            today_count += 1
        d = item.get("domain", "")
        if d:
            domain_set.add(d)

    return {
        "total": len(items),
        "today": today_count,
        "domains": len(domain_set),
        "by_source": by_source,
    }


def distinct_domains(days: int = 90) -> list[str]:
    """최근 N일 내 수집된 도메인 목록 (중복 제거, 알파벳순)."""
    items = list_items(days=days)
    domains = sorted({item.get("domain", "") for item in items if item.get("domain")})
    return domains
