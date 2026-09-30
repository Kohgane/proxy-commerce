"""src/db/option_translate_queue_pg.py — J1 옵션 값·상품명 번역기 큐(상품 단위).

PG가 켜져 있으면 `option_translate_queue`(schema_stage16) + `app_state`(stage14), 아니면 **인메모리**(개발·테스트).
리스는 SKIP LOCKED — 워커가 여럿이어도 한 상품을 두 번 잡지 않는다(두 번 잡으면 무료 한도를 두 번 쓴다).
전역 작은 상태(`state_get`/`state_set`)는 이미지 큐 모듈의 것을 그대로 쓴다(같은 `app_state` 표).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.db import pg
from src.db.image_translate_queue_pg import state_get, state_set  # noqa: F401 — 같은 app_state

_LOCK = threading.Lock()
_MEM_Q: dict = {}
_MEM_DAY: dict = {}
_SEQ = [0]


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def _now():
    return datetime.now(timezone.utc)


def reset_for_tests() -> None:
    with _LOCK:
        _MEM_Q.clear()
        _MEM_DAY.clear()
        _SEQ[0] = 0


def enqueue(user_id: str, item_id: str) -> bool:
    """상품 하나를 대기로. 이미 대기·진행 중이면 그대로, 끝난 행은 다시 대기로(새 값이 생겼을 수 있다)."""
    if not _enabled():
        with _LOCK:
            r = _MEM_Q.get(str(item_id))
            if r and r["status"] in ("queued", "running"):
                return False
            _SEQ[0] += 1
            _MEM_Q[str(item_id)] = {"id": (r or {}).get("id") or _SEQ[0], "user_id": str(user_id),
                                    "item_id": str(item_id), "status": "queued", "reason": "",
                                    "attempts": (r or {}).get("attempts", 0), "values_sent": 0,
                                    "created_at": _now(), "started_at": None, "finished_at": None}
            return True
    with pg.tx() as cur:
        cur.execute("INSERT INTO option_translate_queue (user_id, item_id) VALUES (%s,%s) "
                    "ON CONFLICT (item_id) DO UPDATE SET status='queued', reason='', started_at=NULL, "
                    "finished_at=NULL, user_id=EXCLUDED.user_id "
                    "WHERE option_translate_queue.status NOT IN ('queued','running')", (str(user_id), str(item_id)))
        return bool(cur.rowcount)


def lease_next(stale_seconds: int = 300):
    if not _enabled():
        with _LOCK:
            for r in sorted(_MEM_Q.values(), key=lambda x: x["id"]):
                stale = (r["status"] == "running" and r["started_at"]
                         and (_now() - r["started_at"]).total_seconds() > stale_seconds)
                if r["status"] == "queued" or stale:
                    r.update(status="running", started_at=_now(), attempts=r["attempts"] + 1)
                    return dict(r)
        return None
    with pg.tx() as cur:
        cur.execute(
            "UPDATE option_translate_queue SET status='running', started_at=now(), attempts=attempts+1 "
            "WHERE id = (SELECT id FROM option_translate_queue WHERE status='queued' "
            "  OR (status='running' AND started_at < now() - (%s || ' seconds')::interval) "
            "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, user_id, item_id, attempts", (int(stale_seconds),))
        r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "user_id": r[1], "item_id": r[2], "attempts": int(r[3])}


def requeue(job_id) -> None:
    """상한으로 **보내지 않은** 상품을 대기로(시도 수도 되돌림)."""
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q.values():
                if r["id"] == job_id:
                    r.update(status="queued", started_at=None, attempts=max(0, r["attempts"] - 1))
        return
    with pg.tx() as cur:
        cur.execute("UPDATE option_translate_queue SET status='queued', started_at=NULL, "
                    "attempts=GREATEST(attempts-1,0) WHERE id=%s", (job_id,))


def finish(job_id, status: str, reason: str = "", values_sent: int = 0) -> None:
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q.values():
                if r["id"] == job_id:
                    r.update(status=status, reason=str(reason or "")[:300], finished_at=_now(),
                             values_sent=int(values_sent))
        return
    with pg.tx() as cur:
        cur.execute("UPDATE option_translate_queue SET status=%s, reason=%s, values_sent=%s, finished_at=now() "
                    "WHERE id=%s", (status, str(reason or "")[:300], int(values_sent), job_id))


def counts() -> dict:
    out = {"queued": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0}
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q.values():
                out[r["status"]] = out.get(r["status"], 0) + 1
        return out
    with pg.query() as cur:
        cur.execute("SELECT status, count(*) FROM option_translate_queue GROUP BY 1")
        for st, n in cur.fetchall():
            out[st] = int(n)
    return out


def failed_since(since) -> int:
    if not _enabled():
        with _LOCK:
            return sum(1 for r in _MEM_Q.values()
                       if r["status"] == "failed" and r["finished_at"] and r["finished_at"] >= since)
    with pg.query() as cur:
        cur.execute("SELECT count(*) FROM option_translate_queue WHERE status='failed' AND finished_at >= %s", (since,))
        return int(cur.fetchone()[0])


def take_n(day_key: str, cap: int, want: int) -> tuple:
    """오늘 보낸 값 수를 **상한 안에서** `want`만큼 올린다(원자적) — `(granted, count_after)`.

    남은 몫이 `want`보다 적으면 남은 만큼만 준다(한 상품의 일부만 오늘 보내고 나머지는 내일).
    """
    cap, want = int(cap), max(0, int(want))
    if not _enabled():
        with _LOCK:
            n = int(_MEM_DAY.get(day_key) or 0)
            g = max(0, min(want, cap - n))
            _MEM_DAY[day_key] = n + g
            return g, n + g
    with pg.tx() as cur:
        cur.execute("INSERT INTO app_state (key, value) VALUES (%s, '{\"n\":0}'::jsonb) ON CONFLICT (key) DO NOTHING",
                    (day_key,))
        cur.execute("SELECT coalesce((value->>'n')::int,0) FROM app_state WHERE key=%s FOR UPDATE", (day_key,))
        n = int(cur.fetchone()[0])
        g = max(0, min(want, cap - n))
        if g:
            cur.execute("UPDATE app_state SET value=jsonb_set(value, '{n}', to_jsonb(%s::int)), updated_at=now() "
                        "WHERE key=%s", (n + g, day_key))
    return g, n + g


def day_count(day_key: str) -> int:
    if not _enabled():
        with _LOCK:
            return int(_MEM_DAY.get(day_key) or 0)
    return int(state_get(day_key).get("n") or 0)
