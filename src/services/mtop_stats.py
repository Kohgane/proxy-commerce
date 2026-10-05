"""Z3-C(오너 2026-10-05) — 자동 경로 집계: 시도/성공/RGV587/punish/빈 응답/오류 건수 · 경로별 성공률(KST 하루 단위, 3일 누적) ·
그분 첫 10건의 「담은 시각 → 준비 완료 시각」 · 성공한 getdetail 실제 응답 1건(픽스처 교체용).

저장: app_state(카운터는 `take_n`으로 원자적 +1). 진단 화면 `/admin/diagnostics/taobao-mtop`이 읽는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

KINDS = ("ok", "rgv587", "punish", "empty", "error")
ROUTES = ("direct", "relay", "proxy")
_KST = timezone(timedelta(hours=9))
_FIRST = "mtop_auto:first10"
_RECENT = "mtop_auto:recent"
_SAMPLE = "mtop_auto:sample_detail"


def _day(now=None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(_KST).strftime("%Y-%m-%d")


def _key(day: str, route: str, kind: str) -> str:
    return f"mtop_auto:{day}:{route}:{kind}"


def record(route: str, kind: str, now=None) -> None:
    from src.db import option_translate_queue_pg as q
    kind = kind if kind in KINDS else "error"
    q.take_n(_key(_day(now), route, kind), 10 ** 9, 1)


def summary(days: int = 3, now=None) -> Dict:
    """`{days:[…], routes:{route:{ok,rgv587,punish,empty,error,tried,rate}}, total:{…}}` — 최근 `days`일(KST, 오늘 포함)."""
    from src.db import option_translate_queue_pg as q
    now = now or datetime.now(timezone.utc)
    ds = [_day(now - timedelta(days=i)) for i in range(days)]
    routes: Dict[str, Dict] = {}
    total = {k: 0 for k in KINDS}
    for r in ROUTES:
        row = {k: sum(q.day_count(_key(d, r, k)) for d in ds) for k in KINDS}
        row["tried"] = sum(row[k] for k in KINDS)
        if row["tried"]:
            row["rate"] = round(row["ok"] / row["tried"] * 100)
            routes[r] = row
            for k in KINDS:
                total[k] += row[k]
    total["tried"] = sum(total[k] for k in KINDS)
    total["rate"] = round(total["ok"] / total["tried"] * 100) if total["tried"] else None
    return {"days": ds, "routes": routes, "total": total}


def note_item(entry: Dict) -> None:
    """한 건 기록 — 첫 10건은 고정(켠 뒤 처음 들어온 순서), 최근 30건은 굴린다."""
    from src.db import image_translate_queue_pg as st
    first = list((st.state_get(_FIRST) or {}).get("items") or [])
    if len(first) < 10 and not any(e.get("item_id") == entry.get("item_id") for e in first):
        first.append(entry)
        st.state_set(_FIRST, {"items": first})
    recent = [e for e in (st.state_get(_RECENT) or {}).get("items") or [] if e.get("item_id") != entry.get("item_id")]
    st.state_set(_RECENT, {"items": ([entry] + recent)[:30]})


def first_items() -> List[Dict]:
    from src.db import image_translate_queue_pg as st
    out = []
    for e in (st.state_get(_FIRST) or {}).get("items") or []:
        e = dict(e)
        try:
            a = datetime.fromisoformat(str(e.get("collected_at")).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(e.get("done_at")).replace("Z", "+00:00"))
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            e["collected_kst"] = a.astimezone(_KST).strftime("%m-%d %H:%M:%S")
            e["done_kst"] = b.astimezone(_KST).strftime("%m-%d %H:%M:%S")
            e["took_sec"] = max(0, int((b - a).total_seconds()))
        except Exception:
            e.setdefault("collected_kst", str(e.get("collected_at") or "—"))
            e.setdefault("done_kst", str(e.get("done_at") or "—"))
            e["took_sec"] = None
        out.append(e)
    return out


def save_sample(raw: Dict, *, item_id: str = "", route: str = "") -> bool:
    """성공한 getdetail 실제 응답 1건(처음 것만) — 재구성 픽스처를 이걸로 바꾼다."""
    from src.db import image_translate_queue_pg as st
    if not raw or (st.state_get(_SAMPLE) or {}).get("raw"):
        return False
    st.state_set(_SAMPLE, {"raw": raw, "item_id": item_id, "route": route,
                           "at": datetime.now(timezone.utc).isoformat()})
    return True


def sample() -> Dict:
    from src.db import image_translate_queue_pg as st
    return st.state_get(_SAMPLE) or {}
