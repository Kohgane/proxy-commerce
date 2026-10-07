"""Z3-C(오너 2026-10-07): 온바운드 하루 한도에 막힌 상품 — 「이월 대기」에 넣었다가 한도가 풀리면 자동으로 채운다.

- 넣는 때: `taobao_auto.run`이 온바운드에서 `provider_quota`(4013 已超量) 또는 `provider_cap`(우리 상한 — #845 이후
  상한이 키 max로 내려가 4013보다 먼저 걸리는 쪽)을 받으면. 상품 ID·공유 원문·사용자·시각을 남긴다.
- 빼는 때: 자동 수집이 끝남(성공·다른 사유 실패) · 사용자가 「사진 추가」로 직접 채움 · 상품이 지워짐.
- 비우는 때: 워커 틱(기본 10분, `WORKERS_ENABLED` 서비스·리스 1곳) · 「새로 받기」가 막음을 푼 직후.
  오늘(베이징 날짜) 막음이 있거나 남은 한도가 0이면 부르지 않는다 — 건당 과금. 오래된 순으로 그날 유효 상한까지.
  나머지는 다음 날로 그대로 이월.
- 알림: 대기 20건 초과일 때만, 오너(TELEGRAM_CHAT_ID)에게, 하루 한 번.

저장: `app_state` 한 행(`onebound:carry` → {items:[…]}). PG면 넣기·빼기가 SQL 한 문장(원자적) — 서비스·워커가 여럿이어도
같은 상품이 두 번 들어가거나 넣은 게 사라지지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY = "onebound:carry"
_ALERT = "onebound:carry_alert:"         # + 베이징 날짜 → {n, at}
ALERT_OVER = 20
CARRY_KINDS = ("provider_quota", "provider_cap")
WORKER = "onebound-carry"
_KST = timezone(timedelta(hours=9))
_CST = timezone(timedelta(hours=8))
_LOCK = threading.Lock()
_STARTED = {"done": False}


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def _pg_on() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


# ── 큐 ───────────────────────────────────────────────────────────────────────

def items() -> List[Dict[str, Any]]:
    """오래된 순."""
    rows = [r for r in ((_st().state_get(KEY) or {}).get("items") or []) if isinstance(r, dict) and r.get("item_id")]
    return sorted(rows, key=lambda r: str(r.get("at") or ""))


def count() -> int:
    return len(items())


def position(item_id: str) -> int:
    """1부터. 대기에 없으면 0."""
    for i, r in enumerate(items(), 1):
        if str(r.get("item_id")) == str(item_id):
            return i
    return 0


def add(user_id: str, item_id: str, *, url: str = "", share: str = "", kind: str = "") -> int:
    """넣고(이미 있으면 그대로) 대기 순번을 돌려준다."""
    if not (user_id and item_id):
        return 0
    entry = {"item_id": str(item_id), "user_id": str(user_id), "url": str(url or "")[:500],
             "share": str(share or "")[:500], "kind": str(kind or ""), "at": datetime.now(timezone.utc).isoformat()}
    if not _pg_on():
        st = _st()
        with st._LOCK:
            cur = dict(st._MEM_STATE.get(KEY) or {})
            rows = list(cur.get("items") or [])
            if not any(str(r.get("item_id")) == entry["item_id"] for r in rows):
                rows.append(entry)
            st._MEM_STATE[KEY] = {"items": rows}
    else:
        from src.db import pg
        one = json.dumps([entry], ensure_ascii=False)
        probe = json.dumps([{"item_id": entry["item_id"]}])
        with pg.tx() as cur:
            cur.execute(
                "INSERT INTO app_state (key, value, updated_at) VALUES (%s, jsonb_build_object('items', %s::jsonb), now()) "
                "ON CONFLICT (key) DO UPDATE SET value = jsonb_set(COALESCE(app_state.value, '{}'::jsonb), '{items}', "
                "COALESCE(app_state.value->'items', '[]'::jsonb) || %s::jsonb), updated_at=now() "
                "WHERE NOT (COALESCE(app_state.value->'items', '[]'::jsonb) @> %s::jsonb)",
                (KEY, one, one, probe))
    n = count()
    logger.info("[이월 대기] 넣음 item=%s 사유=%s → %d번째(대기 %d건)", item_id, kind, position(item_id), n)
    _maybe_alert(n)
    return position(item_id)


def remove(item_id: str, why: str = "") -> bool:
    if not item_id:
        return False
    before = position(item_id)
    if not before:
        return False
    if not _pg_on():
        st = _st()
        with st._LOCK:
            cur = dict(st._MEM_STATE.get(KEY) or {})
            st._MEM_STATE[KEY] = {"items": [r for r in (cur.get("items") or []) if str(r.get("item_id")) != str(item_id)]}
    else:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute(
                "UPDATE app_state SET value = jsonb_set(value, '{items}', COALESCE((SELECT jsonb_agg(e) FROM "
                "jsonb_array_elements(COALESCE(value->'items', '[]'::jsonb)) e WHERE e->>'item_id' <> %s), '[]'::jsonb)), "
                "updated_at=now() WHERE key=%s", (str(item_id), KEY))
    logger.info("[이월 대기] 뺌 item=%s (%s)", item_id, why or "—")
    return True


def manual_filled(ex: dict) -> bool:
    """사용자가 「사진 추가」로 직접 채웠나(그 상품은 자동으로 다시 부르지 않는다)."""
    man = ex.get("manual_fields") if isinstance(ex.get("manual_fields"), dict) else {}
    return bool(int(ex.get("manual_photos") or 0) or man.get("images"))


# ── 한도·다음 실행 ─────────────────────────────────────────────────────────────

def budget() -> int:
    """오늘(베이징 날짜) 더 부를 수 있는 수 — 막음이 있으면 0."""
    from src.collectors import taobao_provider_onebound as ob
    if ob.quota_block().get("code"):
        return 0
    return max(0, ob.daily_cap() - ob.used_today())


def next_reset(now=None) -> datetime:
    """다음 베이징 자정(= KST 01:00)."""
    cst = (now or datetime.now(timezone.utc)).astimezone(_CST)
    return (cst.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)


def interval() -> int:
    try:
        return max(60, int(os.getenv("ONEBOUND_CARRY_INTERVAL_SECONDS", "600") or 600))
    except ValueError:
        return 600


def next_run_text(now=None) -> str:
    """진단용 한 줄 — 대기 0이면 빈 문자열."""
    if not count():
        return ""
    from src.services import workers as _w
    if not _w.workers_enabled():
        return f"워커 꺼짐({_w.gate_text()}) — 이 서비스에선 안 돌아요"
    if budget() <= 0:
        at = next_reset(now).astimezone(_KST)
        return f"{at:%m-%d %H:%M} KST(베이징 자정 — 한도 리셋) 뒤 첫 틱"
    return f"다음 틱({interval() // 60}분 안)"


# ── 비우기 ─────────────────────────────────────────────────────────────────────

def drain(runner=None) -> Dict[str, Any]:
    """오래된 순으로 남은 한도까지 자동 수집. `{done, failed, manual_skip, gone, left, stopped}`."""
    from src.collectors import taobao_provider_onebound as ob
    from src.seller_console import collect_history_store as store
    if runner is None:
        from src.services.taobao_auto import run as runner
    out = {"done": 0, "failed": 0, "manual_skip": 0, "gone": 0, "left": 0, "stopped": ""}
    for e in items():
        if budget() <= 0:
            out["stopped"] = "quota_block" if ob.quota_block().get("code") else "cap"
            break
        iid, uid = str(e["item_id"]), str(e.get("user_id") or "")
        row = store.get(iid, seller_ids={uid})
        if not row:
            remove(iid, "상품 없음")
            out["gone"] += 1
            continue
        try:
            ex = json.loads(row.get("extra_json") or "{}") or {}
        except Exception:
            ex = {}
        if manual_filled(ex):
            remove(iid, "사진 추가로 직접 채움")
            out["manual_skip"] += 1
            continue
        rec = runner(uid, iid, via="onebound") or {}
        kind = str(rec.get("kind") or "")
        if kind in CARRY_KINDS:                         # 한도에 다시 막힘 — 이 건과 나머지는 그대로 이월
            out["stopped"] = kind
            break
        remove(iid, "자동 수집 " + ("완료" if rec.get("state") == "done" else f"실패({kind or '사유 없음'})"))
        out["done" if rec.get("state") == "done" else "failed"] += 1
    out["left"] = count()
    if any(out[k] for k in ("done", "failed", "manual_skip", "gone")):
        logger.info("[이월 대기] 비움 %s", out)
    return out


def _tick() -> Dict[str, Any]:
    from src.services import workers as _w
    if not count():
        return {}
    if not _w.lease(WORKER, ttl=interval() + 120):
        return {}
    try:
        res = drain()
        _w.record_run(WORKER, res.get("done", 0) + res.get("failed", 0),
                      note=f"남음 {res.get('left', 0)}" + (f" · 멈춤 {res['stopped']}" if res.get("stopped") else ""))
        return res
    finally:
        _w.release(WORKER)


def kick() -> bool:
    """「새로 받기」가 막음을 푼 직후 — 백그라운드로 한 번 비운다(응답은 기다리지 않는다)."""
    from src.services import workers as _w
    if not (count() and _w.workers_enabled()):
        return False
    threading.Thread(target=_safe_tick, daemon=True, name="onebound-carry-kick").start()
    return True


def _safe_tick() -> None:
    try:
        _tick()
    except Exception as exc:                            # noqa: BLE001 — 백그라운드는 죽지 않는다
        logger.warning("[이월 대기] 비우기 실패: %s", exc)


def _loop() -> None:
    while True:
        _safe_tick()
        time.sleep(interval())


def start_if_enabled() -> str:
    """부팅 때 한 번 — 온바운드 자동 경로 + 워커 서비스일 때만 루프를 띄운다. 왜 안 띄웠는지를 돌려준다."""
    from src.services import taobao_auto as _ta
    from src.services import workers as _w
    if not _ta._onebound():
        return "꺼짐 — TAOBAO_DETAIL_PROVIDER가 onebound 아님"
    if not _w.workers_enabled():
        return f"꺼짐 — 이 서비스는 워커 아님({_w.gate_text()})"
    with _LOCK:
        if _STARTED["done"]:
            return "이미 실행 중"
        threading.Thread(target=_loop, daemon=True, name=WORKER).start()
        _STARTED["done"] = True
    return f"실행 — {interval() // 60}분마다"


# ── 알림 ──────────────────────────────────────────────────────────────────────

def _maybe_alert(n: int, now=None) -> bool:
    """대기 20건 초과일 때만 오너에게, 베이징 하루 한 번."""
    if n <= ALERT_OVER:
        return False
    day = (now or datetime.now(timezone.utc)).astimezone(_CST).strftime("%Y-%m-%d")
    st = _st()
    if (st.state_get(_ALERT + day) or {}).get("n"):
        return False
    st.state_set(_ALERT + day, {"n": n, "at": datetime.now(timezone.utc).isoformat()})
    try:
        from src.collectors import taobao_provider_onebound as ob
        cap = max(1, ob.daily_cap())
        msg = (f"온바운드 한도 이월 대기 {n}건(20건 초과) — 하루 상한 {cap}회라 다 채우려면 약 {-(-n // cap)}일. "
               "충전·키 교체가 필요한지 봐 주세요. /admin/diagnostics/taobao-provider")
        from src.notifications.telegram import send_telegram
        return bool(send_telegram(msg, urgency="warning"))
    except Exception as exc:                            # noqa: BLE001
        logger.warning("[이월 대기] 알림 실패: %s", exc)
        return False
