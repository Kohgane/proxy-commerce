"""src/seller_console/collect_history_store.py — 수집 이력 저장소 (Phase 135.2).

Sheets `collect_history` 워크시트 자동 부트스트랩.
컬럼: id | collected_at | source | domain | url | title | image_url | price | currency | status | preview_url | extra_json
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "collect_history"
_HEADERS = [
    "id", "collected_at", "source", "domain", "url", "title",
    "image_url", "price", "currency", "status", "preview_url", "extra_json",
    "seller_id",
]

# 인메모리 폴백 저장소 (GOOGLE_SHEET_ID 없을 때)
_in_memory: list[dict] = []

# ── v45 P2: 시트 쓰기 직렬화 + 429/5xx 지수 백오프 재시도 ──────────────────────
# 증상: 수집 성공률 들쭉날쭉. 원인: Sheets 분당 쿼터(429)를 삼키고 성공/폴백 처리 →
# 전송된 수집이 비영속(durable=False)으로 502되며 '가끔 실패'. 수리: write를 프로세스
# 내에서 직렬화(버스트 완화)하고 429/5xx는 지수 백오프로 최대 3회 재시도. 끝까지 실패하면
# 예외 전파 → 호출자가 정직 실패(인메모리 폴백·502)로 처리. 429/5xx 발생 카운트는 로깅.
_write_lock = threading.Lock()
_quota_stats = {"count_429": 0, "count_5xx": 0, "retries": 0}


def get_quota_stats() -> dict:
    """진단용 — 시트 쓰기 중 관측한 429/5xx·재시도 누적 카운트(부팅 이후)."""
    return dict(_quota_stats)


def _retryable_status(exc) -> Optional[int]:
    """gspread APIError 등에서 재시도 대상 HTTP 상태코드를 뽑는다(아니면 None)."""
    code = getattr(getattr(exc, "response", None), "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return code
    return None


def _sheets_write(fn, *, tries: int = 3, base_delay: float = 0.5):
    """시트 쓰기를 **직렬화 락 + 429/5xx 지수 백오프 재시도**로 감싼다 (v45 P2).

    락은 fn() 실행 순간만 잡고 sleep은 락 밖(다른 쓰기를 막지 않음). 재시도 불가 예외
    (권한·네트워크 등)는 즉시 전파. tries회 소진 시 마지막 예외 전파.
    """
    last = None
    for attempt in range(tries):
        try:
            with _write_lock:
                return fn()
        except Exception as exc:   # noqa: BLE001 — 상태코드로 재시도 판정 후 재전파
            code = _retryable_status(exc)
            if code is None:
                raise
            if code == 429:
                _quota_stats["count_429"] += 1
            else:
                _quota_stats["count_5xx"] += 1
            last = exc
            if attempt < tries - 1:
                _quota_stats["retries"] += 1
                logger.warning("시트 쓰기 재시도 %d/%d (HTTP %s)", attempt + 1, tries - 1, code)
                time.sleep(base_delay * (2 ** attempt))
    logger.warning("시트 쓰기 재시도 %d회 소진 — 최종 실패: %s", tries, last)
    raise last


def _get_worksheet():
    from src.utils.sheets import open_sheet
    return open_sheet(_SHEET_ID, _WS_NAME)


def _read_sheet_records():
    """시트 전체 records — 같은 요청 내 중복 read 제거(요청 범위 캐시, v8 속도).

    한 페이지 렌더에서 list_items/summary/distinct_domains가 같은 시트를 3번 읽던 것을
    요청당 1회로 줄인다. 요청 컨텍스트가 없으면(배치/테스트) 매번 직접 read(스테일 없음).
    """
    ws = _get_worksheet()
    try:
        from flask import g, has_request_context
        if has_request_context():
            cached = getattr(g, "_kgp_ch_rows", None)
            if cached is not None:
                return cached
            recs = ws.get_all_records()
            g._kgp_ch_rows = recs
            return recs
    except Exception:
        pass
    return ws.get_all_records()


def _invalidate_cache():
    """쓰기 후 요청 범위 캐시 무효화(같은 요청 내 후속 read가 최신을 보게)."""
    try:
        from flask import g, has_request_context
        if has_request_context() and hasattr(g, "_kgp_ch_rows"):
            delattr(g, "_kgp_ch_rows")
    except Exception:
        pass


def _all_rows() -> list[dict]:
    """현재 워커가 볼 수 있는 모든 행 = 시트 + 인메모리 합집합(id 기준 dedup).

    핵심(v24 P0): 시트가 설정돼 있어도 append가 시트 쓰기에 실패하면 행이 _in_memory로
    떨어지는데, 기존 list_items/get은 시트만 읽어 그 행을 못 봤다 → '수집 완료' 토스트는
    뜨는데 이력은 0(가짜 성공처럼 보임). 합집합으로 조회하면 저장 위치(시트/메모리)와
    무관하게 같은 워커에서 즉시 보인다. 시트 읽기 실패 시에도 인메모리로 폴백.
    """
    rows: list[dict] = []
    seen: set = set()
    if _SHEET_ID:
        try:
            for r in _read_sheet_records():
                rows.append(r)
                rid = r.get("id")
                if rid:
                    seen.add(rid)
        except Exception as exc:
            logger.warning("수집 이력 조회 실패: %s", exc)
    for r in _in_memory:
        rid = r.get("id")
        if rid and rid in seen:
            continue
        rows.append(r)
        if rid:
            seen.add(rid)
    return rows


def _ensure_headers(ws) -> None:
    try:
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != "id":
            ws.insert_row(_HEADERS, index=1)
        elif "seller_id" not in first_row:
            # 컬럼 추가 마이그레이션 — seller_id 헤더를 끝에 덧붙인다.
            # (기존 데이터 행은 seller_id 공란 = 레거시로 취급)
            ws.update_cell(1, len(_HEADERS), "seller_id")
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
    seller_id: str = "",
    return_durable: bool = False,
):
    """수집 이력 1건 추가.

    Args:
        seller_id: 수집한 셀러 식별자 (멀티유저 격리용). 빈 값이면 레거시/단일 테넌트.
        return_durable: True면 (item_id, durable) 튜플 반환. durable=False는
            **시트가 설정됐는데 쓰기에 실패해 인메모리로만 폴백**된 경우(멀티워커에서
            다른 워커·새로고침엔 안 보임 → '가짜 성공' 위험). v38 P0: 호출자가 이걸 보고
            정직한 실패를 반환할 수 있게 한다.

    Returns:
        생성된 item_id (6바이트 hex), 또는 return_durable=True면 (item_id, durable).
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
        "seller_id": seller_id or "",
    }

    durable = True
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            _ensure_headers(ws)
            # v45 P2: 429/5xx 지수 백오프 재시도 → 분당 쿼터로 인한 '가끔 실패' 회복.
            _sheets_write(lambda: ws.append_row([row_data[h] for h in _HEADERS]))
            _invalidate_cache()
            logger.info("수집 이력 저장: id=%s source=%s domain=%s", item_id, source, domain)
        except Exception as exc:
            logger.warning("수집 이력 Sheets 저장 실패(인메모리 폴백 — 비영속): %s", exc)
            _in_memory.append(row_data)
            durable = False   # v38 P0: 시트 설정됐는데 폴백 = 멀티워커서 안 보임(가짜성공 위험)
    else:
        # 시트 미설정 = 단일 테넌트/개발 의도(인메모리가 저장소). 영속으로 간주.
        _in_memory.append(row_data)

    # v41 STEP 1-0: 모든 쓰기 경로(시트·인메모리)에서 요청 범위 캐시 무효화 → 같은 요청 재조회 부활 방지.
    _invalidate_cache()

    if return_durable:
        return item_id, durable
    return item_id


def list_items(
    *, domain: str = "", source: str = "", days: int = 30, seller_id: Optional[str] = None,
    seller_ids: Optional[set] = None,
) -> list[dict]:
    """수집 이력 목록 반환 (최신순).

    Args:
        domain: 도메인 필터 (빈 문자열 = 전체)
        source: 소스 필터 (extension/bookmarklet/manual/bulk, 빈 문자열 = 전체)
        days: 최근 N일
        seller_id: 셀러 격리 필터. None이면 전체(레거시/단일 테넌트), 값이면 해당 셀러 항목만.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _all_rows()

    result = []
    for row in rows:
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
    """ID로 단건 조회.

    Args:
        seller_id: 지정 시 해당 셀러의 항목만 반환(타 셀러 항목 접근 차단). None이면 검사 안 함.
        seller_ids: 사용자의 식별자 집합(user_id+email) — 별칭 불일치 대비 관용 매칭.
    """
    def _match(row: dict) -> bool:
        if row.get("id") != item_id:
            return False
        _rsid = str(row.get("seller_id", "") or "")
        if seller_ids is not None:
            return _rsid in seller_ids
        if seller_id is not None and _rsid != str(seller_id):
            return False
        return True

    for row in _all_rows():
        if _match(row):
            return dict(row)
    return None


def find_by_product_key(url: str, *, seller_id: Optional[str] = None,
                        seller_ids: Optional[set] = None) -> Optional[dict]:
    """v42 1-3: 같은 상품(정규화 키 일치)이 이미 수집돼 있으면 그 항목을 반환(중복 방지).

    각 행의 url을 그때그때 정규화해 비교 → 예전 행(키 미저장)도 매칭. 셀러 스코프 격리.
    같은 키가 여러 건이면 가장 최근 것을 반환.
    """
    try:
        from src.collectors.product_key import normalize_product_key
    except Exception:
        return None
    key = normalize_product_key(url)
    if not key:
        return None
    matches = []
    for row in _all_rows():
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
    """수집 이력 단건의 필드를 갱신 (Phase 201 — 중간 편집 저장).

    허용 필드: title, image_url, price, currency, status, extra_json.
    seller_id/seller_ids로 본인 항목만 갱신(타 셀러 차단). v32: seller_ids(관용 식별자
    집합)를 주면 별칭(user_id↔email) 불일치로 갱신 0건(가짜 성공)되던 일괄 버튼 버그 방지.

    Returns:
        갱신 성공 여부.
    """
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

    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            _ensure_headers(ws)
            values = ws.get_all_values()
            if values:
                header = values[0]
                col_idx = {h: i for i, h in enumerate(header)}
                id_i = col_idx.get("id")
                sid_i = col_idx.get("seller_id")
                for r, row in enumerate(values[1:], start=2):
                    if id_i is None or id_i >= len(row) or row[id_i] != item_id:
                        continue
                    if sid_i is not None:
                        row_sid = row[sid_i] if sid_i < len(row) else ""
                        if not _scope_ok(row_sid):
                            return False
                    for field, val in updates.items():
                        ci = col_idx.get(field)
                        if ci is not None:
                            # v45 P2: 셀 갱신도 429/5xx 재시도.
                            _sheets_write(lambda c=ci, v=val: ws.update_cell(r, c + 1, v))
                    _invalidate_cache()
                    logger.info("수집 이력 갱신: id=%s fields=%s", item_id, list(updates))
                    return True
        except Exception as exc:
            logger.warning("수집 이력 Sheets 갱신 실패: %s", exc)

    for row in _in_memory:
        if row.get("id") == item_id:
            if not _scope_ok(row.get("seller_id", "")):
                return False
            row.update(updates)
            _invalidate_cache()   # v41 STEP 1-0: 인메모리 갱신도 캐시 무효화
            return True
    return False


def existing_ids(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> set:
    """v41 STEP 1-0 write-then-verify: 주어진 id 중 아직 저장소에 남아있는 것(본인 스코프)을 재읽기로 반환.
    삭제 후 이걸로 검증 → 남아있으면 삭제 미영속(부활)로 정직 판정."""
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
    for row in _all_rows():   # _all_rows는 캐시 무효화 이후 신선 재읽기(시트+인메모리 합집합)
        rid = str(row.get("id"))
        if rid in ids and _scope_ok(row.get("seller_id", "")):
            present.add(rid)
    return present


def _contiguous_blocks(rows: list[int]) -> list[tuple[int, int]]:
    """정렬된 1-based 행 번호를 인접 구간 [(start, end), ...] (end 포함)로 묶는다.

    N개 행을 한 번에 지우기 위한 batchUpdate deleteDimension 구간 생성용.
    예: [2,3,4,7,8] → [(2,4), (7,8)].
    """
    blocks: list[tuple[int, int]] = []
    for r in sorted(rows):
        if blocks and r == blocks[-1][1] + 1:
            blocks[-1] = (blocks[-1][0], r)
        else:
            blocks.append((r, r))
    return blocks


def delete_ids(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> list[str]:
    """수집 이력에서 여러 항목을 삭제하고 **실제 삭제된 id 목록**을 반환 (v45 P1).

    seller_id/seller_ids로 본인 항목만 삭제(타 셀러 차단). v32: seller_ids(관용 식별자
    집합)를 주면 별칭(user_id↔email) 불일치로 삭제 0건 → 재진입 시 부활하던 버그 방지.
    시트와 인메모리(시트 쓰기 실패 폴백분) 양쪽에서 삭제한다.

    v45 P1(★근본 수리): 기존엔 시트에서 **행마다 delete_rows(N회 개별 API 호출)** → 20건
    전체선택 삭제 시 분당 쿼터(429) 초과가 루프 중간에 터지면 일부만 지워지고(부분 실패)
    나머지는 잔존 → "몇 개 남음 · 페이지 왕복 후 부활". 이를 **단일 batchUpdate 1회**
    (인접 행 구간 묶음 + 내림차순 deleteDimension → 원자성·쿼터 절약)로 교체. 삭제된 id를
    응답하도록 해 프론트가 그 목록만 제거하고 재조회로 검증하게 한다.

    Returns:
        실제 삭제된 id 문자열 리스트.
    """
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
    # 1) 시트에서 삭제(설정 시) — 단일 batchUpdate로 전건 원자적 삭제.
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            _ensure_headers(ws)
            values = ws.get_all_values()
            if values:
                header = values[0]
                col_idx = {h: i for i, h in enumerate(header)}
                id_i = col_idx.get("id")
                sid_i = col_idx.get("seller_id")
                to_delete: list[int] = []   # 삭제 대상 1-based 시트 행 번호
                matched_ids: list[str] = []
                for r, row in enumerate(values[1:], start=2):
                    if id_i is None or id_i >= len(row) or row[id_i] not in ids:
                        continue
                    row_sid = row[sid_i] if (sid_i is not None and sid_i < len(row)) else ""
                    if not _scope_ok(row_sid):
                        continue
                    to_delete.append(r)
                    matched_ids.append(str(row[id_i]))
                if to_delete:
                    # 인접 행을 구간으로 묶고, 구간을 **내림차순**(뒤→앞)으로 지워 인덱스 밀림 0.
                    # 요청 전체가 1회 batchUpdate → 루프 중간 429로 인한 부분 삭제 원천 차단.
                    blocks = _contiguous_blocks(to_delete)
                    requests = [
                        {"deleteDimension": {"range": {
                            "sheetId": ws.id,
                            "dimension": "ROWS",
                            "startIndex": start - 1,   # 0-based
                            "endIndex": end,           # exclusive → end(1-based) 포함
                        }}}
                        for (start, end) in reversed(blocks)
                    ]
                    # v45 P2: 삭제 batchUpdate도 429/5xx 재시도(쿼터로 인한 부분 실패 회복).
                    _sheets_write(lambda: ws.spreadsheet.batch_update({"requests": requests}))
                    removed.update(matched_ids)
            if removed:
                _invalidate_cache()
        except Exception as exc:
            logger.warning("수집 이력 Sheets 삭제 실패: %s", exc)

    # 2) 인메모리에서도 삭제(시트 쓰기 실패 폴백분 포함 — v24 합집합과 짝)
    kept: list[dict] = []
    for row in _in_memory:
        rid = str(row.get("id"))
        if rid in ids and _scope_ok(row.get("seller_id", "")):
            removed.add(rid)
            continue
        kept.append(row)
    _in_memory[:] = kept

    # v41 STEP 1-0: 삭제가 있었으면 요청 범위 캐시를 반드시 무효화(시트·인메모리 어느 경로든) → 재조회 부활 방지.
    if removed:
        _invalidate_cache()
        logger.info("수집 이력 삭제: %d건", len(removed))
    return sorted(removed)


def delete(item_ids, *, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> int:
    """delete_ids의 하위호환 래퍼 — 삭제 건수(int) 반환."""
    return len(delete_ids(item_ids, seller_id=seller_id, seller_ids=seller_ids))


def summary(days: int = 30, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> dict:
    """기간별 요약 통계."""
    items = list_items(days=days, seller_id=seller_id, seller_ids=seller_ids)
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


def distinct_domains(days: int = 90, seller_id: Optional[str] = None, seller_ids: Optional[set] = None) -> list[str]:
    """최근 N일 내 수집된 도메인 목록 (중복 제거, 알파벳순)."""
    items = list_items(days=days, seller_id=seller_id, seller_ids=seller_ids)
    domains = sorted({item.get("domain", "") for item in items if item.get("domain")})
    return domains
