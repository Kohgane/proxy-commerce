"""Y15(오너 2026-10-22 순찰 32 「메모리 바닥 상승 — 스레드 아님 확정, 측정만」) — 잡 하나 앞·뒤로 무엇이 남는지 잰다.

- `before()` / `after(snap)`: `gc.get_objects()`를 type별로 세어 **늘어난 상위 10개**(type 이름 · 늘어난 개수 · 크기 합 KB).
  gc가 추적하는 객체(dict·list·사용자 클래스 인스턴스 등)만 센다 — 문자열·bytes 같은 원자 객체는 그 컨테이너 쪽으로 잡힌다.
- `MEM_TRACE=1`일 때만 tracemalloc top 10 diff(줄 단위). 기본은 꺼짐(켜면 할당마다 비용이 붙는다).
- `module_caches()`: `src.*` 모듈 수준의 dict·list·set·deque와 `lru_cache` 함수 — 이름 · 파일 · 개수 · 크기(KB, 한 단계) · 상한.
  상한이 없는(=`maxsize` 없음, 일반 dict·list) 큰 것이 범인 후보.

측정 실패는 잡을 막지 않는다(빈 값). 고치는 코드는 여기 없다 — 표를 보고 다음 순찰에서 자를 곳을 정한다.
"""
from __future__ import annotations

import gc
import os
import sys
from collections import Counter, deque
from typing import Any, Dict, List, Optional

_TRACE_ON = False
_SCAN_CAP = 20000            # 컨테이너 하나의 한 단계 크기를 잴 때 최대 원소 수(큰 캐시도 측정이 잡을 멈추지 않게)


def _trace_wanted() -> bool:
    return os.getenv("MEM_TRACE", "").strip() in ("1", "true", "yes")


def _counts() -> tuple:
    n: Counter = Counter()
    b: Counter = Counter()
    for o in gc.get_objects():
        t = type(o).__name__
        n[t] += 1
        try:
            b[t] += sys.getsizeof(o)
        except Exception:                                        # noqa: BLE001
            pass
    return n, b


def before() -> Dict[str, Any]:
    global _TRACE_ON
    snap: Dict[str, Any] = {}
    try:
        snap["n"], snap["b"] = _counts()
    except Exception:                                            # noqa: BLE001
        snap["n"], snap["b"] = Counter(), Counter()
    if _trace_wanted():
        try:
            import tracemalloc
            if not tracemalloc.is_tracing():
                tracemalloc.start(10)
                _TRACE_ON = True
            snap["trace"] = tracemalloc.take_snapshot()
        except Exception:                                        # noqa: BLE001
            pass
    return snap


def type_growth(snap: Dict[str, Any], top: int = 10) -> List[list]:
    """`[[type, 늘어난 개수, 늘어난 크기 KB], …]` — 개수 기준 상위 `top`."""
    try:
        n1, b1 = _counts()
    except Exception:                                            # noqa: BLE001
        return []
    n0, b0 = snap.get("n") or Counter(), snap.get("b") or Counter()
    rows = [[t, n1[t] - n0.get(t, 0), round((b1[t] - b0.get(t, 0)) / 1024, 1)] for t in n1 if n1[t] - n0.get(t, 0) > 0]
    rows.sort(key=lambda r: (-r[1], -r[2]))
    return rows[:top]


def trace_growth(snap: Dict[str, Any], top: int = 10) -> List[list]:
    """`MEM_TRACE=1`일 때만 — `[[파일:줄, 늘어난 KB, 늘어난 개수], …]`."""
    if "trace" not in snap:
        return []
    try:
        import tracemalloc
        cur = tracemalloc.take_snapshot()
        out = []
        for st in cur.compare_to(snap["trace"], "lineno")[:top]:
            fr = st.traceback[0] if st.traceback else None
            where = f"{os.path.relpath(fr.filename) if fr else '?'}:{fr.lineno if fr else 0}"
            out.append([where, round(st.size_diff / 1024, 1), st.count_diff])
        return out
    except Exception:                                            # noqa: BLE001
        return []


def _shallow_kb(obj) -> float:
    try:
        size = sys.getsizeof(obj)
        if isinstance(obj, dict):
            for i, (k, v) in enumerate(obj.items()):
                if i >= _SCAN_CAP:
                    break
                size += sys.getsizeof(k) + sys.getsizeof(v)
        elif isinstance(obj, (list, tuple, set, frozenset, deque)):
            for i, v in enumerate(obj):
                if i >= _SCAN_CAP:
                    break
                size += sys.getsizeof(v)
        return round(size / 1024, 1)
    except Exception:                                            # noqa: BLE001
        return 0.0


def module_caches(prefixes=("src.",), top: Optional[int] = None, min_len: int = 1) -> List[dict]:
    """`[{name, file, kind, len, kb, maxsize}]` — 크기(KB) 큰 순(`top`이면 그만큼). `maxsize` None = 상한 없음(lru는 None이면 무한).
    lru_cache는 원소 크기를 못 재므로 kb가 None — 크기 순 뒤에 개수 순으로 온다."""
    out: List[dict] = []
    for mname, mod in list(sys.modules.items()):
        if not mname.startswith(tuple(prefixes)) or mod is None:
            continue
        fname = os.path.relpath(getattr(mod, "__file__", "") or "?")
        try:
            items = list(vars(mod).items())
        except Exception:                                        # noqa: BLE001
            continue
        for attr, val in items:
            if attr.startswith("__"):
                continue
            try:
                if hasattr(val, "cache_info") and callable(getattr(val, "cache_info")):
                    ci = val.cache_info()
                    if ci.currsize >= min_len:
                        out.append({"name": f"{mname}.{attr}", "file": fname, "kind": "lru_cache", "len": ci.currsize,
                                    "kb": None, "maxsize": ci.maxsize})
                elif isinstance(val, (dict, list, set, deque)) and len(val) >= min_len:
                    out.append({"name": f"{mname}.{attr}", "file": fname, "kind": type(val).__name__, "len": len(val),
                                "kb": _shallow_kb(val), "maxsize": getattr(val, "maxlen", None)})
            except Exception:                                    # noqa: BLE001
                continue
    out.sort(key=lambda r: (-(r["kb"] or 0), -r["len"]))
    return out[:top] if top else out


def after(snap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """잡 끝 한 번 — `{types, caches, trace?}`(기록용 짧은 모양)."""
    snap = snap or {}
    out: Dict[str, Any] = {"types": type_growth(snap)}
    try:
        allc = module_caches()
        pick = [r for r in allc if r["kind"] != "lru_cache"][:15] + [r for r in allc if r["kind"] == "lru_cache"][:10]
        out["caches"] = [[r["name"], r["kind"], r["len"], r["kb"], r["maxsize"]] for r in pick]
    except Exception:                                            # noqa: BLE001
        out["caches"] = []
    tr = trace_growth(snap)
    if tr:
        out["trace"] = tr
    return out
