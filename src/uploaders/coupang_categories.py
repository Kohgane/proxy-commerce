"""Y7-E(오너 2026-10-08) — 쿠팡 노출 카테고리 **전체 경로**(예: 패션의류잡화>여성패션>여성의류>정장/세트>여성 캐주얼 세트).

쿠팡 예측(`categorization/predict`)은 리프 이름 하나(`predictedCategoryName` = 「여성 캐주얼 세트」)만 준다.
리프 끝 낱말 「세트」만으로 네이버를 맞추면 식품>통조림/캔>세트가 1등으로 올라온다(오너 폰 23:37 실측).
그래서 쿠팡 「카테고리 목록조회」(`GET …/marketplace/meta/display-categories` — 노출 카테고리 전체, 경로 출처:
PyPI `coupang` 래퍼 1.4.2 `get_categories`)로 ID → 전체 경로 표를 만든다.

- 하루 1회, **백그라운드**에서 받는다(Z8 — 요청 스레드에서 큰 목록을 받지 않는다). 못 받았으면 경로 없이(리프 이름만).
- 응답 모양은 원문으로 확인하기 전이라 너그럽게 읽는다: 노드 코드 `displayItemCategoryCode`·`displayCategoryCode`·`code`·`id`,
  이름 `name`, 아이 `child`·`children`·`subCategories`. 루트(ROOT·코드 0)는 경로에서 뺀다.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

STATE_KEY = "coupang_category_paths"
TTL_SEC = 24 * 3600
RETRY_SEC = 300.0
LIST_PATH = "/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories"
BACKGROUND = True
_LOCK = threading.Lock()
_MEM: Dict = {"data": None}
_REFRESH: Dict = {"thread": None, "last_fail": 0.0, "why": ""}


def _store():
    from src.db import image_translate_queue_pg as st
    return st


def _code(n: dict) -> str:
    for k in ("displayItemCategoryCode", "displayCategoryCode", "code", "id"):
        if n.get(k) not in (None, ""):
            return str(n[k])
    return ""


def _kids(n: dict) -> list:
    for k in ("child", "children", "subCategories"):
        v = n.get(k)
        if isinstance(v, list):
            return v
    return []


def flatten(root) -> Dict[str, str]:
    """노드 트리 → `{코드: 「1단계>…>리프」}` (루트·코드 0은 경로에서 뺀다)."""
    out: Dict[str, str] = {}
    stack = [(n, []) for n in (root if isinstance(root, list) else [root])]
    while stack:
        n, trail = stack.pop()
        if not isinstance(n, dict):
            continue
        code, name = _code(n), str(n.get("name") or "").strip()
        is_root = code in ("", "0") or name.upper() == "ROOT"
        here = trail if is_root else trail + [name]
        if not is_root and code:
            out[code] = ">".join(here)
        for c in _kids(n):
            stack.append((c, here))
    return out


def _fetch() -> Optional[Dict[str, str]]:
    try:
        from src.channel_sync.coupang_uploader import make_uploader
        up, _acct = make_uploader()
        if not (up.access_key and up.secret_key):
            _REFRESH["why"] = "쿠팡 키 없음"
            return None
        res = up._api_request("GET", LIST_PATH)
    except Exception as exc:                                      # noqa: BLE001
        _REFRESH["why"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return None
    data = res.get("data") if isinstance(res, dict) else None
    paths = flatten(data) if data else {}
    if not paths:
        _REFRESH["why"] = "응답에서 카테고리를 읽지 못함: " + str(res)[:200]
        return None
    return paths


def _fetch_and_store() -> Optional[dict]:
    paths = _fetch()
    if not paths:
        with _LOCK:
            _REFRESH["last_fail"] = time.time()
        logger.warning("[쿠팡 카테고리] 경로 표 받기 실패 — %s", _REFRESH["why"])
        return None
    d = {"fetched_at": time.time(), "paths": paths}
    try:
        _store().state_set(STATE_KEY, d)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("[쿠팡 카테고리] 저장 실패(메모리만): %s", exc)
    with _LOCK:
        _MEM["data"] = d
    logger.info("[쿠팡 카테고리] 경로 표 갱신 — %d개", len(paths))
    return d


def start_background_refresh(*, force: bool = False) -> bool:
    with _LOCK:
        t = _REFRESH["thread"]
        if t is not None and t.is_alive():
            return False
        if not force and time.time() - float(_REFRESH["last_fail"] or 0) < RETRY_SEC:
            return False
        t = threading.Thread(target=_fetch_and_store, daemon=True, name="coupang-category-paths")
        _REFRESH["thread"] = t
    t.start()
    return True


def table() -> Optional[dict]:
    """저장된 경로 표 — 없거나 하루 지났으면 백그라운드로 받기 시작하고 지금 있는 것(없으면 None)."""
    now = time.time()
    with _LOCK:
        d = _MEM["data"]
    if not d:
        try:
            d = _store().state_get(STATE_KEY) or None
        except Exception:
            d = None
        if d:
            with _LOCK:
                _MEM["data"] = d
    if d and now - float(d.get("fetched_at") or 0) < TTL_SEC:
        return d
    if not BACKGROUND:
        return _fetch_and_store() or d
    start_background_refresh()
    return d


def path_of(code: str) -> str:
    d = table() or {}
    return str((d.get("paths") or {}).get(str(code or ""), ""))


def reset() -> None:
    with _LOCK:
        _MEM["data"] = None
        _REFRESH.update(thread=None, last_fail=0.0, why="")
