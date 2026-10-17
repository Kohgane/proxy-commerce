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
           "status, preview_url, extra_json, user_id, last_action_at, attn_n")

# 속도(v46 STEP1): 목록 쿼리는 대형 컬럼(extra_json의 이미지 40장·상세설명·리뷰·스펙)을 통째로
#   끌지 않고, 목록 렌더에 필요한 작은 필드만 SQL에서 축약(jsonb_build_object) → 전송량·직렬화 급감.
#   대표 썸네일은 image_url 컬럼(이미 존재) + images 폴백은 첫 1장만.
_LEAN_EXTRA = (
    "jsonb_build_object("
    "'title_ko', extra_json->'title_ko',"
    "'title_en', extra_json->'title_en',"
    "'title', extra_json->'title',"
    "'uploaded', extra_json->'uploaded',"
    "'price_status', extra_json->'price_status',"
    "'warnings', extra_json->'warnings',"
    "'collect_status', extra_json->'collect_status',"
    # v87-W4: 목록에서도 리뷰·평점 표시(작은 스칼라만 — 대형 reviews 배열은 통째로 안 끈다).
    "'rating', extra_json->'rating',"
    "'review_count', extra_json->'review_count',"
    "'recollected_at', extra_json->'recollected_at',"
    # v87-W6: 목록 번역 상태 3분(번역함/원문/실패) 표시용 스칼라.
    "'translated', extra_json->'translated',"
    "'translate_error', extra_json->'translate_error',"
    "'translate_requested', extra_json->'translate_requested',"
    # C-F14: 보강 축(등록 가능/보강 진행)을 목록이 **알 수 있게** 실어 보낸다.
    #   없으면 목록이 완전 수집 잣대로 부분 초안을 재고 「실패」라 적는다(실측).
    "'gate_ready', extra_json->'gate_ready',"
    "'enrich_state', extra_json->'enrich_state',"
    "'enrich_blocked_reason', extra_json->'enrich_blocked_reason',"
    "'enrich_attempts', extra_json->'enrich_attempts',"
    "'mode', extra_json->'mode',"
    # F49-T 5부: 목록 타일 보강 여부(enrich_axes) · 이미지 완료 기준(「이미지 부족」 배지) — 작은 값만.
    "'enriched', extra_json->'enriched',"
    "'image_check', extra_json->'image_check',"
    # Y10: 「등록 안 함」 — 목록 칩 「등록 보류: 사유」(작은 dict)
    "'risk_skip', extra_json->'risk_skip',"
    # Y12-A: 목록 「마지막 동작」·뱃지 「실패」·「손댈 것」 — 작은 값만
    "'coupang_detail_sync', extra_json->'coupang_detail_sync',"
    "'attn', extra_json->'attn',"
    "'images', CASE WHEN jsonb_typeof(extra_json->'images')='array' AND jsonb_array_length(extra_json->'images')>0 "
    "THEN jsonb_build_array(extra_json->'images'->0) ELSE '[]'::jsonb END,"
    # lean은 이미지를 **첫 장만** 싣는다 → 개수를 세면 늘 1이다. 실제 장수는 SQL이 세서 보낸다.
    "'images_count', CASE WHEN jsonb_typeof(extra_json->'images')='array' "
    "THEN jsonb_array_length(extra_json->'images') ELSE 0 END"
    ") AS extra_json"
)
_SELECT_LEAN = ("id, created_at, source, domain, url, title, image_url, price, currency, "
                "status, preview_url, " + _LEAN_EXTRA + ", user_id, last_action_at, attn_n")


def _shape(t) -> dict:
    """DB 행 튜플 → Sheets 스토어와 동일 모양의 dict."""
    (rid, created_at, source, domain, url, title, image_url, price, currency,
     status, preview_url, extra_json, user_id) = t[:13]
    last_action_at, attn_n = (t[13], t[14]) if len(t) > 14 else (None, 0)
    return {
        "last_action_at": last_action_at.astimezone(timezone.utc).isoformat() if last_action_at else "",
        "attn_n": int(attn_n or 0),
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
           extra: dict = None, seller_id: str = "", return_durable: bool = False, raw_url: str = "",
           last_action_at=None, attn_n: int = 0):
    """수집 1건 추가(트랜잭션 커밋 후에만 성공=durable). product_key 유니크로 중복 방지.
    Y12-A: `last_action_at`·`attn_n`(목록 정렬·「손댈 것만」 열)도 함께 넣는다."""
    pkey = _product_key(url)
    domain = urlparse(url).netloc
    extra_json = json.dumps(extra or {}, ensure_ascii=False)
    item_id = None
    with pg.tx() as cur:
        if pkey:
            cur.execute(
                """INSERT INTO collect_history
                   (user_id, product_key, source, domain, url, title, image_url, price, currency, status, preview_url, extra_json, raw_url,
                    last_action_at, attn_n)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                   ON CONFLICT (user_id, product_key)
                     WHERE product_key IS NOT NULL AND product_key <> '' AND deleted_at IS NULL
                   DO NOTHING
                   RETURNING id""",
                (seller_id, pkey, source, domain, url, title, image, str(price or ""),
                 currency, status, preview_url, extra_json, raw_url or "", last_action_at or None, int(attn_n or 0)))
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
                   (user_id, product_key, source, domain, url, title, image_url, price, currency, status, preview_url, extra_json, raw_url,
                    last_action_at, attn_n)
                   VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                   RETURNING id""",
                (seller_id, source, domain, url, title, image, str(price or ""),
                 currency, status, preview_url, extra_json, raw_url or "", last_action_at or None, int(attn_n or 0)))
            item_id = str(cur.fetchone()[0])
        if item_id and not preview_url:
            cur.execute("UPDATE collect_history SET preview_url=%s WHERE id=%s AND preview_url=''",
                        (f"/seller/collect/preview/{item_id}", item_id))
    durable = item_id is not None   # 커밋됐으면 항상 영속(Sheets 폴백 없음)
    return (item_id, durable) if return_durable else item_id


_ACTION_AT = "COALESCE(last_action_at, created_at)"


def list_items(*, domain: str = "", source: str = "", days: int = 30,
               seller_id=None, seller_ids=None, limit=None, offset=0, lean=False, order="created", attn_only=False) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sc, params = _scope(seller_id, seller_ids)
    _cols = _SELECT_LEAN if lean else _SELECT      # 속도: 목록은 대형 컬럼 제외한 축약 projection
    _at = _ACTION_AT if order == "action" else "created_at"     # Y12-A: 마지막 동작 최신순(기간도 그 기준)
    sql = (f"SELECT {_cols} FROM collect_history WHERE deleted_at IS NULL "
           f"AND {_at} >= %s AND {sc}")
    args = [cutoff] + params
    if attn_only:
        sql += " AND attn_n > 0"
    if domain:
        sql += " AND domain = %s"; args.append(domain)
    if source:
        sql += " AND source = %s"; args.append(source)
    sql += f" ORDER BY {_at} DESC"
    # 속도: 기본 뷰(최신순·필터없음)는 SQL LIMIT/OFFSET로 그 페이지만 가져온다(전체 스캔 회피).
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"; args.append(int(limit)); args.append(int(offset))
    with pg.query() as cur:
        cur.execute(sql, args)
        return [_shape(t) for t in cur.fetchall()]


def count_items(*, days: int = 30, seller_ids=None, order="action", attn_only=False) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sc, params = _scope(None, seller_ids)
    _at = _ACTION_AT if order == "action" else "created_at"
    sql = f"SELECT count(*) FROM collect_history WHERE deleted_at IS NULL AND {_at} >= %s AND {sc}"
    if attn_only:
        sql += " AND attn_n > 0"
    with pg.query() as cur:
        cur.execute(sql, [cutoff] + params)
        return int((cur.fetchone() or (0,))[0] or 0)


def ids_for_attention_backfill(limit: int = 500) -> list:
    """Y12-A 일회성 — 목록 정렬·「손댈 것」 열이 아직 비었고 등록 기록·등록 보류가 있는 상품 id(전 셀러)."""
    with pg.query() as cur:
        cur.execute("SELECT id::text, user_id FROM collect_history WHERE deleted_at IS NULL AND last_action_at IS NULL "
                    "AND (extra_json ? 'uploaded' OR extra_json ? 'risk_skip') ORDER BY created_at DESC LIMIT %s", [int(limit)])
        return [(r[0], r[1]) for r in cur.fetchall()]


def set_attention(item_id: str, last_action_at, attn_n: int, attn: dict) -> bool:
    """Y12-A 일회성 — 열 두 개와 `extra.attn`만 바꾼다(그 밖의 extra 칸·수집 원본은 손대지 않는다)."""
    with pg.tx() as cur:
        cur.execute("UPDATE collect_history SET last_action_at=%s, attn_n=%s, "
                    "extra_json = jsonb_set(extra_json, '{attn}', %s::jsonb, true) WHERE id::text=%s RETURNING id",
                    [last_action_at or None, int(attn_n or 0), json.dumps(attn or {}, ensure_ascii=False), str(item_id)])
        return cur.fetchone() is not None


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
    # Y12-A: 목록 「마지막 동작 최신순」·「손댈 것만」 열(값 그대로 — None이면 created_at으로 본다)
    if "last_action_at" in fields:
        sets.append("last_action_at = %s"); args.append(fields["last_action_at"] or None)
    if "attn_n" in fields:
        sets.append("attn_n = %s"); args.append(int(fields["attn_n"] or 0))
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
