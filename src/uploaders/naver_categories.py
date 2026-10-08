"""Y7-B(오너 2026-10-08) — 네이버 리프 카테고리 가드.

실측(오너 폰 16:26 KST, 플리츠 세트 셰고가): `POST /v2/products` → 400
`invalidInputs[originProduct.leafCategoryId] NotValid 「리프 카테고리ID 항목이 유효하지 않습니다」`.
원인(코드·운영 DB): 상품 `category_code=CLO` → 업로더 `CATEGORY_MAP['CLO']='50000000'`(최상위 「패션의류」).
`CATEGORY_MAP`은 전부 최상위 ID라 어떤 상품이든 리프가 아니다 — 운영 DB 등록 기록에 스마트스토어 성공은 0건.
「고코스모스엔 『자동 배정 — 카테고리 CLO』」는 **스토어 배정 규칙**(`smartstore_routing.json`: 고코스모스 categories에
CLO가 있고 셰고가엔 없음)이지 카테고리 ID 매핑이 아니다 — 두 스토어 모두 같은 `50000000`을 보냈다.

여기서 하는 일:
- 네이버 카테고리 트리(`GET /v1/categories`, 문서: id·name·wholeCategoryName·last)를 **하루 1회** 받아
  `app_state`에 캐시한다.
- 등록이 보낼 `leafCategoryId`를 고르는 순서: 오너가 지정한 `naver_category_id` → 정본 사전 매칭(상품명).
  둘 다 없으면 **보류**(`category_unset`) — 정본 기본 리프(`50004132`)로 옷을 보내면 등록 후 카테고리를 못 바꾼다
  (네이버 `NotChangable.product.category`).
- 고른 ID가 캐시에서 `last=true`가 아니면 **보류**(`category_not_leaf`) — 네이버까지 가서 400을 받지 않게.
  캐시를 못 받았으면(키·네트워크) 판정 못 함 = 막지 않는다(네이버가 답한다).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATE_KEY = "naver_categories"
TTL_SEC = 24 * 3600
REASON_NOT_LEAF = "category_not_leaf"
REASON_UNSET = "category_unset"
_MEM: Dict = {"at": 0.0, "data": None}
_LOCK = threading.Lock()


def _store():
    from src.db import image_translate_queue_pg as st
    return st


def _fetch(account: str = "") -> Optional[list]:
    """네이버에서 전체 카테고리 — 실패하면 None(사유는 로그)."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    accounts = [account] if account else []
    accounts += [a for a in NaverSmartStoreUploader.ACCOUNT_PREFIXES if a not in accounts]
    for acct in accounts:
        try:
            up = NaverSmartStoreUploader(account=acct)
            if not (up.client_id and up.client_secret):
                continue
            res = up._api_request("GET", "/v1/categories")
        except Exception as exc:                            # noqa: BLE001
            logger.warning("[네이버 카테고리] %s 조회 예외: %s", acct, exc)
            continue
        if isinstance(res, list):
            return res
        logger.warning("[네이버 카테고리] %s 조회 실패: %s", acct, str((res or {}).get("error") or res)[:200])
    return None


def _pack(rows: list) -> dict:
    leaves, parents = {}, []
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        cid = str(r["id"])
        if r.get("last"):
            leaves[cid] = str(r.get("wholeCategoryName") or r.get("name") or "")
        else:
            parents.append(cid)
    return {"fetched_at": time.time(), "leaves": leaves, "parents": parents}


def tree(*, refresh: bool = False, account: str = "") -> Optional[dict]:
    """`{fetched_at, leaves: {id: 전체 이름}, parents: [id]}` — 하루 1회 갱신. 못 받았으면 마지막 저장본, 그것도 없으면 None."""
    now = time.time()
    with _LOCK:
        d = _MEM["data"]
        if d and not refresh and now - float(d.get("fetched_at") or 0) < TTL_SEC:
            return d
    if not d:
        try:
            d = _store().state_get(STATE_KEY) or None
        except Exception:
            d = None
    if d and not refresh and now - float(d.get("fetched_at") or 0) < TTL_SEC:
        with _LOCK:
            _MEM["data"] = d
        return d
    rows = _fetch(account)
    if rows:
        d = _pack(rows)
        try:
            _store().state_set(STATE_KEY, d)
        except Exception as exc:                            # noqa: BLE001
            logger.warning("[네이버 카테고리] 저장 실패(메모리만): %s", exc)
        logger.info("[네이버 카테고리] 갱신 — 리프 %d · 상위 %d", len(d["leaves"]), len(d["parents"]))
    with _LOCK:
        _MEM["data"] = d
    return d


def leaf_state(cid: str, *, account: str = "") -> str:
    """`leaf` · `not_leaf`(상위 카테고리) · `unknown_id`(트리에 없음) · `unknown`(트리를 못 받음)."""
    t = tree(account=account)
    if not t or not (t.get("leaves") or t.get("parents")):
        return "unknown"
    cid = str(cid or "").strip()
    if cid in (t.get("leaves") or {}):
        return "leaf"
    if cid in set(t.get("parents") or []):
        return "not_leaf"
    return "unknown_id"


def name_of(cid: str) -> str:
    t = tree() or {}
    return str((t.get("leaves") or {}).get(str(cid or ""), ""))


def search(q: str, limit: int = 30) -> List[Dict[str, str]]:
    """리프만 — 낱말(공백 구분)이 전부 전체 이름에 들어 있는 것. 짧은 이름 먼저."""
    t = tree() or {}
    words = [w for w in str(q or "").split() if w]
    if not words:
        return []
    hits = [(cid, whole) for cid, whole in (t.get("leaves") or {}).items() if all(w in whole for w in words)]
    hits.sort(key=lambda x: (len(x[1]), x[1]))
    return [{"id": cid, "name": whole} for cid, whole in hits[:limit]]


def pick(product: dict) -> Tuple[str, str]:
    """`(leafCategoryId, 출처)` — 출처: manual(오너 지정) · pattern(정본 사전 매칭) · ""(못 정함)."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    p = product or {}
    manual = str(p.get("naver_category_id") or "").strip()
    if manual:
        return manual, "manual"
    hit = SS.match_category(p.get("title") or p.get("title_ko") or "")
    return (hit, "pattern") if hit else ("", "")


def hold(product: dict, *, account: str = "") -> Optional[Dict[str, str]]:
    """보류 `{code, line}` 또는 None. 판정 못 함(트리 없음)은 막지 않는다."""
    cid, src = pick(product)
    if not cid:
        return {"code": REASON_UNSET,
                "line": "네이버 카테고리를 정하지 못했어요 — 카테고리를 다시 지정하세요(카테고리 지정 →)"}
    st = leaf_state(cid, account=account)
    if st == "not_leaf":
        return {"code": REASON_NOT_LEAF,
                "line": f"네이버 카테고리 {cid}는 하위 분류가 있는 상위 카테고리예요(리프 아님) — 카테고리를 다시 지정하세요(카테고리 지정 →)"}
    if st == "unknown_id":
        return {"code": REASON_NOT_LEAF,
                "line": f"네이버 카테고리 {cid}가 네이버 목록에 없어요 — 카테고리를 다시 지정하세요(카테고리 지정 →)"}
    return None


def reset() -> None:
    """테스트·진단용 — 메모리 캐시만 비운다(저장본은 그대로)."""
    with _LOCK:
        _MEM.update(at=0.0, data=None)


def picker_url(item_id: str) -> str:
    return f"/seller/collect/{item_id}/naver-category" if item_id else ""
