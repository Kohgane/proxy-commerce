"""src/seller_console/collect_history_store.py — 수집 이력 저장소 (PG-only 전환).

1차 저장소 = **Supabase Postgres**(src.db.collect_history_pg). 런타임 Sheets 폴백은 제거됐다
(오너 PG-only 지시). PG 미설정 시에는 **인메모리**(개발/테스트 전용, 비영속)만 쓴다 —
프로덕션(APP_ENV=production)에서 PG가 없으면 부팅 자체가 실패한다(order_webhook 부팅 가드).
Sheets는 읽기전용 백업(일 1회 덤프, src.db.backup)으로만 강등됐다.

이전의 Sheets 우회코드(P1 batchUpdate 삭제·P2 429 백오프 재시도)는 PG 소프트삭제·트랜잭션
커밋으로 원천 소멸해 제거했다.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_WS_NAME = "collect_history"
_HEADERS = [
    "id", "collected_at", "source", "domain", "url", "title",
    "image_url", "price", "currency", "status", "preview_url", "extra_json",
    "seller_id",
]

# 인메모리 저장소 — PG 미설정(개발/테스트) 전용. 비영속(워커 로컬).
_in_memory: list[dict] = []


def _pg_backend():
    """Postgres 백엔드 활성 시 모듈 반환(스키마 1회 부트스트랩), 아니면 None(인메모리).

    DATABASE_URL(6543 풀러) 설정 + psycopg + 연결 성공일 때만. 미설정이면 인메모리(비영속).
    """
    try:
        from src.db import pg as _pgmod
        if _pgmod.pg_enabled():
            _pgmod.init_schema()
            from src.db import collect_history_pg as _chpg
            return _chpg
    except Exception as exc:
        logger.warning("PG 백엔드 확인 실패 — 인메모리 폴백: %s", exc)
    return None


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
    seller_id: str = "",
    return_durable: bool = False,
):
    """수집 이력 1건 추가. PG면 트랜잭션 커밋 후 durable, 아니면 인메모리(개발/테스트)."""
    _b = _pg_backend()
    if _b:
        return _b.append(source=source, url=url, title=title, image=image, price=price,
                         currency=currency, status=status, preview_url=preview_url,
                         extra=extra, seller_id=seller_id, return_durable=return_durable)

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
        "seller_id": seller_id or "",
    }
    _in_memory.append(row_data)
    if return_durable:
        return item_id, True
    return item_id


def list_items(
    *, domain: str = "", source: str = "", days: int = 30, seller_id: Optional[str] = None,
    seller_ids: Optional[set] = None,
) -> list[dict]:
    """수집 이력 목록 반환 (최신순)."""
    _b = _pg_backend()
    if _b:
        return _b.list_items(domain=domain, source=source, days=days, seller_id=seller_id, seller_ids=seller_ids)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = []
    for row in _in_memory:
        if row.get("collected_at", "") < cutoff:
            continue
        if domain and row.get("domain", "") != domain:
            continue
        if source and row.get("source", "") != source:
            continue
        _rsid = str(row.get("seller_id", "") or "")
        if seller_ids is not None:
            if _rsid not in seller_ids:
                continue
        elif seller_id is not None and _rsid != str(seller_id):
            continue
        result.append(dict(row))
    result.sort(key=lambda r: r.get("collected_at", ""), reverse=True)
    return result


def get(item_id: str, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> Optional[dict]:
    """ID로 단건 조회(셀러 스코프 격리)."""
    _b = _pg_backend()
    if _b:
        return _b.get(item_id, seller_id=seller_id, seller_ids=seller_ids)

    def _match(row: dict) -> bool:
        if row.get("id") != item_id:
            return False
        _rsid = str(row.get("seller_id", "") or "")
        if seller_ids is not None:
            return _rsid in seller_ids
        if seller_id is not None and _rsid != str(seller_id):
            return False
        return True

    for row in _in_memory:
        if _match(row):
            return dict(row)
    return None


def find_by_product_key(url: str, *, seller_id: Optional[str] = None,
                        seller_ids: Optional[set] = None) -> Optional[dict]:
    """같은 상품(정규화 키 일치)이 이미 수집돼 있으면 그 항목 반환(중복 방지)."""
    _b = _pg_backend()
    if _b:
        return _b.find_by_product_key(url, seller_id=seller_id, seller_ids=seller_ids)
    try:
        from src.collectors.product_key import normalize_product_key
    except Exception:
        return None
    key = normalize_product_key(url)
    if not key:
        return None
    matches = []
    for row in _in_memory:
        _rsid = str(row.get("seller_id", "") or "")
        if seller_ids is not None:
            if _rsid not in seller_ids:
                continue
        elif seller_id is not None and _rsid != str(seller_id):
            continue
        if normalize_product_key(row.get("url", "")) == key:
            matches.append(row)
    if not matches:
        return None
    matches.sort(key=lambda r: r.get("collected_at", ""), reverse=True)
    return dict(matches[0])


def update(item_id: str, *, seller_id: Optional[str] = None,
           seller_ids: Optional[set] = None, **fields) -> bool:
    """수집 이력 단건 필드 갱신. 허용: title, image_url, price, currency, status, extra_json."""
    _b = _pg_backend()
    if _b:
        return _b.update(item_id, seller_id=seller_id, seller_ids=seller_ids, **fields)

    allowed = {"title", "image_url", "price", "currency", "status", "extra_json"}
    updates = {k: ("" if v is None else str(v)) for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    def _scope_ok(row_sid) -> bool:
        rsid = str(row_sid or "")
        if seller_ids is not None:
            return rsid in seller_ids
        if seller_id is not None:
            return rsid == str(seller_id)
        return True

    for row in _in_memory:
        if row.get("id") == item_id:
            if not _scope_ok(row.get("seller_id", "")):
                return False
            row.update(updates)
            return True
    return False


def existing_ids(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> set:
    """write-then-verify: 주어진 id 중 아직 저장소에 남아있는 것(본인 스코프)을 재읽기로 반환."""
    _b = _pg_backend()
    if _b:
        return _b.existing_ids(item_ids, seller_id=seller_id, seller_ids=seller_ids)
    ids = {str(i) for i in (item_ids or []) if str(i).strip()}
    if not ids:
        return set()

    def _scope_ok(row_sid) -> bool:
        rsid = str(row_sid or "")
        if seller_ids is not None:
            return rsid in seller_ids
        if seller_id is not None:
            return rsid == str(seller_id)
        return True

    present = set()
    for row in _in_memory:
        rid = str(row.get("id"))
        if rid in ids and _scope_ok(row.get("seller_id", "")):
            present.add(rid)
    return present


def delete_ids(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> list[str]:
    """여러 항목 삭제 후 **실제 삭제된 id 목록** 반환(셀러 스코프 격리).

    PG는 소프트삭제(단일 UPDATE) — 행밀림·부분삭제(P1) 원천 소멸. 인메모리는 리스트에서 제거.
    """
    _b = _pg_backend()
    if _b:
        return _b.delete_ids(item_ids, seller_id=seller_id, seller_ids=seller_ids)
    ids = {str(i) for i in (item_ids or []) if str(i).strip()}
    if not ids:
        return []

    def _scope_ok(row_sid) -> bool:
        rsid = str(row_sid or "")
        if seller_ids is not None:
            return rsid in seller_ids
        if seller_id is not None:
            return rsid == str(seller_id)
        return True

    removed: set[str] = set()
    kept: list[dict] = []
    for row in _in_memory:
        rid = str(row.get("id"))
        if rid in ids and _scope_ok(row.get("seller_id", "")):
            removed.add(rid)
            continue
        kept.append(row)
    _in_memory[:] = kept
    if removed:
        logger.info("수집 이력 삭제: %d건", len(removed))
    return sorted(removed)


def delete(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> int:
    """delete_ids의 하위호환 래퍼 — 삭제 건수(int) 반환."""
    return len(delete_ids(item_ids, seller_id=seller_id, seller_ids=seller_ids))


def summary(days: int = 30, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> dict:
    """기간별 요약 통계."""
    items = list_items(days=days, seller_id=seller_id, seller_ids=seller_ids)
    by_source: dict[str, int] = {"extension": 0, "bookmarklet": 0, "manual": 0, "bulk": 0}
    today_prefix = datetime.now(timezone.utc).date().isoformat()
    today_count = 0
    domain_set: set[str] = set()
    for item in items:
        src = item.get("source", "")
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
    return {"total": len(items), "today": today_count, "domains": len(domain_set), "by_source": by_source}


def distinct_domains(days: int = 90, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> list[str]:
    """최근 N일 내 수집된 도메인 목록 (중복 제거, 알파벳순)."""
    items = list_items(days=days, seller_id=seller_id, seller_ids=seller_ids)
    return sorted({item.get("domain", "") for item in items if item.get("domain")})
