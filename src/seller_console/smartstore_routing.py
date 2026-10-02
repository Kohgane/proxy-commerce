"""U0b(오너 2026-10-02 정정) — 스마트스토어 두 스토어: 셰고가(`chezgoga`, 고가네 축) · 고코스모스(`gocosmos`, 우주대행 축).

- **배정**: 상품 카테고리·상품명 낱말로 한 스토어를 고른다(표 `smartstore_routing.json` — 원격 JSON, 관리자 덮어쓰기
  `app_state smartstore:routing`). 근거가 없으면 빈 값 — 지어서 고르지 않는다(오너가 화면에서 고름). 「양쪽 다」는 화면에서 둘 다 체크.
- **승인**: 스토어마다 `SMARTSTORE_<STORE>_APPROVED`(없으면 예전 전체 플래그 `SMARTSTORE_APPROVED`). 미승인은 **보류**
  (「커머스API 미승인 — 신청 대기」) — 막는 게 아니라 무엇을 기다리는지 말한다.
- **한도**: 스토어당 판매중·판매대기·품절 합계 1,000(볼트 「스마트스토어 등록 한도」). 숫자는 커머스 API(`products/search`
  `totalElements`)로만 센다 — 못 세면 「조회 불가」(지어내지 않음). 10분 캐시.
- **니치·고단가만**: 표의 `min_price_krw` — 볼트에 수치 결정이 없어 기본 **꺼짐**(null). 오너가 값을 넣으면 그 아래는 보류.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_FILE = Path(__file__).with_name("smartstore_routing.json")
_STATE_KEY = "smartstore:routing"
STORES = ("chezgoga", "gocosmos")
_TTL = 60.0
_COUNT_TTL = 600.0
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "rules": None}
_counts: Dict[str, tuple] = {}


def rules() -> dict:
    now = time.monotonic()
    with _lock:
        if _cache["rules"] is not None and now - _cache["at"] < _TTL:
            return _cache["rules"]
    r = json.loads(_FILE.read_text(encoding="utf-8"))
    try:
        from src.db import image_translate_queue_pg as st
        over = (st.state_get(_STATE_KEY) or {}).get("rules")
        if isinstance(over, dict) and over:
            r = dict(r, **over)
    except Exception:
        pass
    with _lock:
        _cache.update(at=now, rules=r)
    return r


def reset_cache() -> None:
    with _lock:
        _cache.update(at=0.0, rules=None)
        _counts.clear()


def store_label(store: str) -> str:
    return str(((rules().get("stores") or {}).get(store) or {}).get("label") or store)


def approved(store: str = "") -> bool:
    """그 스토어의 커머스API 승인. 스토어 플래그가 있으면 그것, 없으면 예전 전체 플래그."""
    def _on(v):
        return str(v or "").strip().lower() in ("1", "true", "yes", "on")
    if store:
        own = os.getenv(f"SMARTSTORE_{store.upper()}_APPROVED")
        if own is not None and own.strip() != "":
            return _on(own)
    return _on(os.getenv("SMARTSTORE_APPROVED"))


def assign_store(product: dict) -> dict:
    """`{store, why}` — 카테고리 코드가 맞으면 2점, 상품명 낱말 하나당 1점. 동점·0점이면 빈 값(오너가 고름)."""
    p = product or {}
    cat = str(p.get("category_code") or p.get("category") or "").strip().upper()
    title = " ".join(str(p.get(k) or "") for k in ("title_ko", "coupang_name", "title"))
    score, why = {}, {}
    for st, conf in (rules().get("stores") or {}).items():
        sc, hits = 0, []
        if cat and cat in (conf.get("categories") or []):
            sc += 2
            hits.append(f"카테고리 {cat}")
        for kw in conf.get("keywords") or []:
            if kw and re.search(re.escape(kw), title, re.I):
                sc += 1
                hits.append(kw)
        score[st], why[st] = sc, hits
    ranked = sorted(score.items(), key=lambda x: -x[1])
    if not ranked or ranked[0][1] == 0 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return {"store": "", "why": "카테고리·상품명으로 정하지 못했어요 — 직접 골라 주세요"}
    st = ranked[0][0]
    return {"store": st, "why": "자동 배정 — " + ", ".join(why[st][:3])}


def price_hold(product: dict) -> str:
    """니치·고단가만(오너 U0 정정) — `min_price_krw`가 있을 때만. 없으면(기본) 빈 문자열."""
    floor = rules().get("min_price_krw")
    if not floor:
        return ""
    try:
        price = float((product or {}).get("sell_price_krw") or (product or {}).get("price_krw") or 0)
    except (TypeError, ValueError):
        price = 0
    if price and price < float(floor):
        return f"스마트스토어는 고단가만 — 판매가 {int(price):,}원이 기준 {int(floor):,}원보다 낮아요"
    return ""


def store_count(store: str, *, fetch=None) -> Optional[int]:
    """한도 대상(판매중·판매대기·품절) 상품 수. 못 세면 None. 10분 캐시."""
    now = time.monotonic()
    hit = _counts.get(store)
    if hit and now - hit[0] < _COUNT_TTL:
        return hit[1]
    n = None
    try:
        if fetch is None:
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            n = NaverSmartStoreUploader(account=store).count_products(rules().get("limit_statuses") or None)
        else:
            n = fetch(store)
    except Exception as exc:
        logger.warning("[스스 한도] %s 상품 수 조회 실패: %s", store, exc)
        n = None
    if n is not None:
        _counts[store] = (now, n)
    return n


def limit_state(store: str, *, fetch=None) -> dict:
    """`{count, limit, full, text}` — 화면·사전검증 공용."""
    limit = int(rules().get("limit") or 1000)
    n = store_count(store, fetch=fetch) if approved(store) else None
    if n is None:
        why = "커머스API 미승인" if not approved(store) else "조회 실패"
        return {"count": None, "limit": limit, "full": False, "text": f"{store_label(store)} ?/{limit:,} — 조회 불가({why})"}
    return {"count": n, "limit": limit, "full": n >= limit, "text": f"{store_label(store)} {n:,}/{limit:,}"}


def store_choices(product: Optional[dict] = None) -> list:
    """마켓 선택 줄 재료 — `[{code, store, label, business, ready, approved, assigned, note, limit_text}]`."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    assigned = assign_store(product or {}) if product else {"store": "", "why": ""}
    out = []
    for st in STORES:
        conf = (rules().get("stores") or {}).get(st) or {}
        try:
            up = NaverSmartStoreUploader(account=st)
            ready = bool(up.client_id and up.client_secret)
        except Exception:
            ready = False
        ok = approved(st)
        note = "" if ok else "커머스API 미승인 — 신청 대기"
        if assigned.get("store") == st:
            note = (assigned["why"] + (" · " + note if note else ""))
        out.append({"code": f"smartstore:{st}", "store": st, "label": f"스마트스토어 — {conf.get('label') or st}",
                    "business": conf.get("business") or "", "ready": ready, "approved": ok,
                    "assigned": assigned.get("store") == st, "note": note,
                    "limit_text": limit_state(st)["text"] if ok else ""})
    return out
