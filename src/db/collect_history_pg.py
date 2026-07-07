"""src/db/collect_history_pg.py — 수집이력 Postgres 백엔드(이관 1단계).

collect_history_store의 공개 API를 그대로 미러(행 dict 모양·시그니처 동일)해, PG가 설정되면
collect_history_store가 이리로 위임한다. Sheets 회귀 없음(미설정이면 이 모듈 미사용).

핵심 이득(Sheets 대비):
- 삭제=소프트삭제(deleted_at) 단일 UPDATE — 행밀림/부활 원천 소멸(P1).
- 트랜잭션 커밋 후에만 성공 — 쿼터 429·비영속 폴백 소멸(P2).
- product_key 유니크 인덱스 — 같은 상품 재수집 중복 0(1-3).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from . import pg

logger = logging.getLogger(__name__)

# 행 dict가 노출하는 키(Sheets 스토어와 동일 — 템플릿/호출자 호환).
_SELECT = ("id, created_at, source, domain, url, title, image_url, price, currency, "
           "status, preview_url, extra_json, user_id")


def _shape(t) -> dict:
    """DB 행 튜플 → Sheets 스토어와 동일 모양의 dict."""
    (rid, created_at, source, domain, url, title, image_url, price, currency,
     status, preview_url, extra_json, user_id) = t
    return {
        "id": str(rid),
        "collected_at": created_at.astimezone(timezone.utc).isoformat() if created_at else "",
        "source": source or "",
        "domain": domain or "",
        "url": url or "",
        "title": title or "",
        "image_url": image_url or "",
        "price": price or "",
        "currency": currency or "",
        "status": status or "",
        "preview_url": preview_url or "",
        "extra_json": json.dumps(extra_json or {}, ensure_ascii=False) if not isinstance(extra_json, str) else extra_json,
        "seller_id": user_id or "",
    }


def _scope(seller_id, seller_ids):
    """(sql, params) — user_id 스코프 필터. None이면 전체."""
    if seller_ids is not None:
        return "user_id = ANY(%s)", [list(seller_ids)]
    if seller_id is not None:
        return "user_id = %s", [str(seller_id)]
    return "TRUE", []


def _product_key(url: str):
    try:
        from src.collectors.product_key import normalize_product_key
        return normalize_product_key(url) or None
    except Exception:
        return None


def append(*, source: str, url: str, title: str, image: str = "", price: str = "",
           currency: str = "", status: str = "ok", preview_url: str = "",
           extra: dict = None, seller_id: str = "", return_durable: bool = False):
    """수집 1건 추가(트랜잭션 커밋 후에만 성공=durable). product_key 유니크로 중복 방지."""
    pkey = _product_key(url)
    domain = urlparse(url).netloc
    extra_json = json.dumps(extra or {}, ensure_ascii=False)
    item_id = None
    with pg.tx() as cur:
        if pkey:
            cur.execute(
                """INSERT INTO collect_history
                   (user_id, product_key, source, domain, url, title, image_url, price, currency, status, preview_url, extra_json)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (user_id, product_key)
                     WHERE product_key IS NOT NULL AND product_key <> '' AND deleted_at IS NULL
                   DO NOTHING
                   RETURNING id""",
                (seller_id, pkey, source, domain, url, title, image, str(price or ""),
                 currency, status, preview_url, extra_json))
            row = cur.fetchone()
            if row:
                item_id = str(row[0])
            else:
                cur.execute("SELECT id FROM collect_history WHERE user_id=%s AND product_key=%s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1",
                            (seller_id, pkey))
                r2 = cur.fetchone()
                item_id = str(r2[0]) if r2 else None
        else:
            cur.execute(
                """INSERT INTO collect_history
                   (user_id, product_key, source, domain, url, title, image_url, price, currency, status, preview_url, extra_json)
                   VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   RETURNING id""",
                (seller_id, source, domain, url, title, image, str(price or ""),
                 currency, status, preview_url, extra_json))
            item_id = str(cur.fetchone()[0])
        if item_id and not preview_url:
            cur.execute("UPDATE collect_history SET preview_url=%s WHERE id=%s AND preview_url=''",
                        (f"/seller/collect/preview/{item_id}", item_id))
    durable = item_id is not None   # 커밋됐으면 항상 영속(Sheets 폴백 없음)
    return (item_id, durable) if return_durable else item_id


def list_items(*, domain: str = "", source: str = "", days: int = 30,
               seller_id=None, seller_ids=None, limit=None, offset=0) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sc, params = _scope(seller_id, seller_ids)
    sql = (f"SELECT {_SELECT} FROM collect_history WHERE deleted_at IS NULL "
           f"AND created_at >= %s AND {sc}")
    args = [cutoff] + params
    if domain:
        sql += " AND domain = %s"; args.append(domain)
    if source:
        sql += " AND source = %s"; args.append(source)
    sql += " ORDER BY created_at DESC"
    # 속도: 기본 뷰(최신순·필터없음)는 SQL LIMIT/OFFSET로 그 페이지만 가져온다(전체 스캔 회피).
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"; args.append(int(limit)); args.append(int(offset))
    with pg.query() as cur:
        cur.execute(sql, args)
        return [_shape(t) for t in cur.fetchall()]


def get(item_id: str, seller_id=None, seller_ids=None):
    sc, params = _scope(seller_id, seller_ids)
    with pg.query() as cur:
        cur.execute(f"SELECT {_SELECT} FROM collect_history WHERE id::text=%s AND deleted_at IS NULL AND {sc}",
                    [str(item_id)] + params)
        r = cur.fetchone()
        return _shape(r) if r else None


def find_by_product_key(url: str, *, seller_id=None, seller_ids=None):
    pkey = _product_key(url)
    if not pkey:
        return None
    sc, params = _scope(seller_id, seller_ids)
    with pg.query() as cur:
        cur.execute(f"SELECT {_SELECT} FROM collect_history WHERE product_key=%s AND deleted_at IS NULL AND {sc} ORDER BY created_at DESC LIMIT 1",
                    [pkey] + params)
        r = cur.fetchone()
        return _shape(r) if r else None


def delete_ids(item_ids, *, seller_id=None, seller_ids=None) -> list:
    """소프트삭제(deleted_at) — 단일 UPDATE(원자적, 행밀림 0). 실제 삭제된 id 목록 반환."""
    ids = [str(i) for i in (item_ids or []) if str(i).strip()]
    if not ids:
        return []
    sc, params = _scope(seller_id, seller_ids)
    with pg.tx() as cur:
        cur.execute(f"UPDATE collect_history SET deleted_at=now() WHERE id::text = ANY(%s) AND deleted_at IS NULL AND {sc} RETURNING id::text",
                    [ids] + params)
        return [r[0] for r in cur.fetchall()]


def delete(item_ids, *, seller_id=None, seller_ids=None) -> int:
    return len(delete_ids(item_ids, seller_id=seller_id, seller_ids=seller_ids))


def existing_ids(item_ids, *, seller_id=None, seller_ids=None) -> set:
    ids = [str(i) for i in (item_ids or []) if str(i).strip()]
    if not ids:
        return set()
    sc, params = _scope(seller_id, seller_ids)
    with pg.query() as cur:
        cur.execute(f"SELECT id::text FROM collect_history WHERE id::text = ANY(%s) AND deleted_at IS NULL AND {sc}",
                    [ids] + params)
        return {r[0] for r in cur.fetchall()}


def update(item_id: str, *, seller_id=None, seller_ids=None, **fields) -> bool:
    allowed = {"title", "image_url", "price", "currency", "status", "extra_json"}
    updates = {k: ("" if v is None else str(v)) for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    sc, params = _scope(seller_id, seller_ids)
    sets, args = [], []
    for k, v in updates.items():
        if k == "extra_json":
            sets.append("extra_json = %s::jsonb"); args.append(v)
        else:
            sets.append(f"{k} = %s"); args.append(v)
    with pg.tx() as cur:
        cur.execute(f"UPDATE collect_history SET {', '.join(sets)} WHERE id::text=%s AND deleted_at IS NULL AND {sc} RETURNING id",
                    args + [str(item_id)] + params)
        return cur.fetchone() is not None


def summary(days: int = 30, seller_id=None, seller_ids=None) -> dict:
    # 속도: 전체 행을 파이썬으로 가져와 세지 않고 SQL 집계(count/FILTER) 1회로 — 스캔 대신 인덱스 count.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sc, params = _scope(seller_id, seller_ids)
    sql = (
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE created_at >= %s) AS today, "
        "count(DISTINCT domain) FILTER (WHERE domain <> '') AS domains, "
        "count(*) FILTER (WHERE source IN ('extension','chrome_extension')) AS ext, "
        "count(*) FILTER (WHERE source = 'bookmarklet') AS bm, "
        "count(*) FILTER (WHERE source = 'manual') AS manual, "
        "count(*) FILTER (WHERE source IN ('bulk','bulk_collect')) AS bulk "
        f"FROM collect_history WHERE deleted_at IS NULL AND created_at >= %s AND {sc}"
    )
    with pg.query() as cur:
        cur.execute(sql, [today_start, cutoff] + params)
        r = cur.fetchone() or (0, 0, 0, 0, 0, 0, 0)
    return {"total": r[0] or 0, "today": r[1] or 0, "domains": r[2] or 0,
            "by_source": {"extension": r[3] or 0, "bookmarklet": r[4] or 0,
                          "manual": r[5] or 0, "bulk": r[6] or 0}}


def distinct_domains(days: int = 90, seller_id=None, seller_ids=None) -> list:
    # 속도: SQL DISTINCT로 도메인만 — 전체 행 파이썬 로드 제거.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sc, params = _scope(seller_id, seller_ids)
    sql = (f"SELECT DISTINCT domain FROM collect_history WHERE deleted_at IS NULL "
           f"AND created_at >= %s AND {sc} AND domain <> '' ORDER BY domain")
    with pg.query() as cur:
        cur.execute(sql, [cutoff] + params)
        return [r[0] for r in cur.fetchall()]


def count_total(days: int = 3650, seller_id=None, seller_ids=None) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sc, params = _scope(seller_id, seller_ids)
    with pg.query() as cur:
        cur.execute(f"SELECT count(*) FROM collect_history WHERE deleted_at IS NULL AND created_at >= %s AND {sc}",
                    [cutoff] + params)
        return int(cur.fetchone()[0])
