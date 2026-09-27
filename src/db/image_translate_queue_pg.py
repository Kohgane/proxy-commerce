"""src/db/image_translate_queue_pg.py — D3-8 이미지 번역 자동 큐(장 단위) + 전역 작은 상태.

PG가 켜져 있으면 `image_translate_queue`·`app_state`(schema_stage14), 아니면 **인메모리**(개발·테스트).
리스는 SKIP LOCKED — 워커가 여럿이어도 같은 장을 두 번 잡지 않는다(두 번 잡으면 두 번 청구된다).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from src.db import pg

_LOCK = threading.Lock()
_MEM_Q: list = []
_MEM_STATE: dict = {}
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
        _MEM_STATE.clear()
        _SEQ[0] = 0


# ── 큐 ───────────────────────────────────────────────────────────────────────

def enqueue(user_id: str, item_id: str, pages) -> int:
    """`pages=[(kind, idx)]` — 이미 있는 장(같은 상품·종류·번호)은 건너뛴다. 새로 넣은 장 수."""
    pages = [(str(k), int(i)) for k, i in pages]
    if not _enabled():
        n = 0
        with _LOCK:
            have = {(r["item_id"], r["kind"], r["idx"]) for r in _MEM_Q}
            for k, i in pages:
                if (str(item_id), k, i) in have:
                    continue
                _SEQ[0] += 1
                _MEM_Q.append({"id": _SEQ[0], "user_id": str(user_id), "item_id": str(item_id), "kind": k,
                               "idx": i, "status": "queued", "reason": "", "attempts": 0,
                               "created_at": _now(), "started_at": None, "finished_at": None})
                n += 1
        return n
    n = 0
    with pg.tx() as cur:
        for k, i in pages:
            cur.execute("INSERT INTO image_translate_queue (user_id, item_id, kind, idx) VALUES (%s,%s,%s,%s) "
                        "ON CONFLICT (item_id, kind, idx) DO NOTHING", (str(user_id), str(item_id), k, i))
            n += cur.rowcount or 0
    return n


def lease_next(stale_seconds: int = 300):
    """다음 장 하나를 `running`으로 잡는다(오래 멈춘 running은 다시 잡는다). 없으면 None."""
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q:
                stale = (r["status"] == "running" and r["started_at"]
                         and (_now() - r["started_at"]).total_seconds() > stale_seconds)
                if r["status"] == "queued" or stale:
                    r.update(status="running", started_at=_now(), attempts=r["attempts"] + 1)
                    return dict(r)
        return None
    with pg.tx() as cur:
        cur.execute(
            "UPDATE image_translate_queue SET status='running', started_at=now(), attempts=attempts+1 "
            "WHERE id = (SELECT id FROM image_translate_queue WHERE status='queued' "
            "  OR (status='running' AND started_at < now() - (%s || ' seconds')::interval) "
            "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, user_id, item_id, kind, idx, attempts", (int(stale_seconds),))
        r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "user_id": r[1], "item_id": r[2], "kind": r[3], "idx": int(r[4]), "attempts": int(r[5])}


def requeue(job_id) -> None:
    """상한·일시정지로 **보내지 않은** 장을 대기로 되돌린다(시작하지 않았으니 시도 수도 되돌림)."""
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q:
                if r["id"] == job_id:
                    r.update(status="queued", started_at=None, attempts=max(0, r["attempts"] - 1))
        return
    with pg.tx() as cur:
        cur.execute("UPDATE image_translate_queue SET status='queued', started_at=NULL, "
                    "attempts=GREATEST(attempts-1,0) WHERE id=%s", (job_id,))


def finish(job_id, status: str, reason: str = "") -> None:
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q:
                if r["id"] == job_id:
                    r.update(status=status, reason=str(reason or "")[:300], finished_at=_now())
        return
    with pg.tx() as cur:
        cur.execute("UPDATE image_translate_queue SET status=%s, reason=%s, finished_at=now() WHERE id=%s",
                    (status, str(reason or "")[:300], job_id))


def counts(item_id: str = "") -> dict:
    """`{queued, running, done, failed, skipped}` — 상품 하나 또는 전체."""
    out = {"queued": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0}
    if not _enabled():
        with _LOCK:
            for r in _MEM_Q:
                if item_id and r["item_id"] != str(item_id):
                    continue
                out[r["status"]] = out.get(r["status"], 0) + 1
        return out
    with pg.query() as cur:
        if item_id:
            cur.execute("SELECT status, count(*) FROM image_translate_queue WHERE item_id=%s GROUP BY 1", (str(item_id),))
        else:
            cur.execute("SELECT status, count(*) FROM image_translate_queue GROUP BY 1")
        for st, n in cur.fetchall():
            out[st] = int(n)
    return out


def started_since(since) -> int:
    """`since` 이후 **시작한** 장 수(실패·재시도 포함 — 시작할 때마다 센다: 시도 수 합)."""
    if not _enabled():
        with _LOCK:
            return sum(r["attempts"] for r in _MEM_Q if r["started_at"] and r["started_at"] >= since)
    with pg.query() as cur:
        cur.execute("SELECT coalesce(sum(attempts),0) FROM image_translate_queue WHERE started_at >= %s", (since,))
        return int(cur.fetchone()[0])


def failed_since(since) -> int:
    if not _enabled():
        with _LOCK:
            return sum(1 for r in _MEM_Q if r["status"] == "failed" and r["finished_at"] and r["finished_at"] >= since)
    with pg.query() as cur:
        cur.execute("SELECT count(*) FROM image_translate_queue WHERE status='failed' AND finished_at >= %s", (since,))
        return int(cur.fetchone()[0])


# ── 전역 작은 상태 ────────────────────────────────────────────────────────────

def state_get(key: str) -> dict:
    if not _enabled():
        with _LOCK:
            return dict(_MEM_STATE.get(key) or {})
    with pg.query() as cur:
        cur.execute("SELECT value FROM app_state WHERE key=%s", (key,))
        r = cur.fetchone()
    v = r[0] if r else {}
    return v if isinstance(v, dict) else (json.loads(v) if v else {})


def state_set(key: str, value: dict) -> None:
    if not _enabled():
        with _LOCK:
            _MEM_STATE[key] = dict(value or {})
        return
    with pg.tx() as cur:
        cur.execute("INSERT INTO app_state (key, value, updated_at) VALUES (%s, %s::jsonb, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
                    (key, json.dumps(value or {}, ensure_ascii=False)))


def take_start(day_key: str, cap: int) -> tuple:
    """오늘 시작 수를 **상한 아래일 때만** 1 올린다(원자적) — `(took, count_after)`.

    워커가 여럿이어도 상한을 넘겨 시작하지 않는다. 실패·재시도도 시작할 때마다 센다(오너 기준).
    """
    cap = int(cap)
    if not _enabled():
        with _LOCK:
            v = dict(_MEM_STATE.get(day_key) or {})
            n = int(v.get("n") or 0)
            if n >= cap:
                return False, n
            v["n"] = n + 1
            _MEM_STATE[day_key] = v
            return True, n + 1
    with pg.tx() as cur:
        cur.execute("INSERT INTO app_state (key, value) VALUES (%s, '{\"n\":0}'::jsonb) ON CONFLICT (key) DO NOTHING",
                    (day_key,))
        cur.execute("UPDATE app_state SET value=jsonb_set(value, '{n}', to_jsonb(coalesce((value->>'n')::int,0)+1)), "
                    "updated_at=now() WHERE key=%s AND coalesce((value->>'n')::int,0) < %s "
                    "RETURNING (value->>'n')::int", (day_key, cap))
        r = cur.fetchone()
        if r:
            return True, int(r[0])
        cur.execute("SELECT coalesce((value->>'n')::int,0) FROM app_state WHERE key=%s", (day_key,))
        r2 = cur.fetchone()
    return False, int(r2[0]) if r2 else 0


def day_count(day_key: str) -> int:
    return int(state_get(day_key).get("n") or 0)
