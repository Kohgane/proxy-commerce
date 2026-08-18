"""src/db/translation_jobs_pg.py — v88-B: 백그라운드 번역 작업 큐 스토어(Supabase).

설계 = docs/design/background-translation.md. stage1 관례(pg.tx 커밋=durable, pg.query 읽기).
불변: 체인·요청예산 캡·쿼터 회계 무손대. PG 미가동이면 이 모듈 미사용(라우트가 기존 동기 경로로 폴백).

상태: pending → running(SKIP LOCKED 리스) → success | failed. 재시도(원인 4분: auth/quota=터미널, rate_limit/transient=backoff).
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from . import pg


def enabled() -> bool:
    return pg.pg_enabled()


def _idem(user_id: str, item_id: str) -> str:
    return f"{user_id}|{item_id}"


def enqueue(user_id: str, item_id: str, *, priority: int = 0, max_attempts: int = 3) -> dict:
    """번역 작업 등록(요청 경로 — 체인 미호출). 활성 중복이면 기존 작업 재사용(재클릭 폭주 방어).

    반환: {job_id, status}. status ∈ {pending, running, success}(이미 있으면 그 상태).
    """
    idem = _idem(user_id, item_id)
    with pg.tx() as cur:
        cur.execute(
            """INSERT INTO translation_jobs (user_id, item_id, status, priority, max_attempts, idem_key)
               VALUES (%s,%s,'pending',%s,%s,%s)
               ON CONFLICT (idem_key) WHERE status IN ('pending','running') AND deleted_at IS NULL
               DO NOTHING
               RETURNING id::text, status""",
            (user_id, item_id, int(priority), int(max_attempts), idem))
        row = cur.fetchone()
        if row:
            return {"job_id": row[0], "status": row[1]}
        # 활성 작업이 이미 있음 → 그 작업 반환(가장 최근 활성).
        cur.execute(
            """SELECT id::text, status FROM translation_jobs
               WHERE idem_key=%s AND status IN ('pending','running') AND deleted_at IS NULL
               ORDER BY created_at DESC LIMIT 1""", (idem,))
        r2 = cur.fetchone()
        if r2:
            return {"job_id": r2[0], "status": r2[1]}
    # 활성은 없으나 유니크가 막았을 수 있음(레이스) — 최근 작업 아무거나.
    with pg.query() as cur:
        cur.execute("SELECT id::text, status FROM translation_jobs WHERE idem_key=%s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1", (idem,))
        r3 = cur.fetchone()
    return {"job_id": r3[0], "status": r3[1]} if r3 else {"job_id": None, "status": "error"}


def lease(limit: int, *, worker_id: str, stale_seconds: int = 90) -> list:
    """드레인 — pending(또는 리스 만료된 running)을 FOR UPDATE SKIP LOCKED로 잡아 running 마킹.

    멀티워커 안전(SKIP LOCKED). 반환: [{job_id, user_id, item_id, attempts, max_attempts}].
    """
    out = []
    with pg.tx() as cur:
        cur.execute(
            f"""SELECT id::text, user_id, item_id, attempts, max_attempts
                FROM translation_jobs
                WHERE deleted_at IS NULL
                  AND (status='pending'
                       OR (status='running' AND locked_at < now() - interval '{int(stale_seconds)} seconds'))
                ORDER BY priority DESC, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s""", (int(limit),))
        rows = cur.fetchall()
        for r in rows:
            jid = r[0]
            cur.execute(
                """UPDATE translation_jobs
                   SET status='running', locked_by=%s, locked_at=now(), started_at=COALESCE(started_at, now())
                   WHERE id::text=%s""", (worker_id, jid))
            out.append({"job_id": jid, "user_id": r[1], "item_id": r[2],
                        "attempts": r[3], "max_attempts": r[4]})
    return out


def complete(job_id: str, *, provider: str, result: dict) -> bool:
    """성공 커밋 — status=success, result_json, finished_at."""
    with pg.tx() as cur:
        cur.execute(
            """UPDATE translation_jobs
               SET status='success', provider=%s, result_json=%s::jsonb, cause='', error='',
                   finished_at=now()
               WHERE id::text=%s AND status='running' RETURNING id""",
            (provider, json.dumps(result or {}, ensure_ascii=False), job_id))
        return cur.fetchone() is not None


def fail(job_id: str, *, cause: str, error: str, retryable: bool) -> str:
    """실패 처리 — 재시도 가능(rate_limit/transient) & attempts<max면 pending 복귀, 아니면 터미널 failed.

    반환: 'pending'(재시도 예약) | 'failed'(터미널).
    """
    with pg.tx() as cur:
        cur.execute("SELECT attempts, max_attempts FROM translation_jobs WHERE id::text=%s FOR UPDATE", (job_id,))
        row = cur.fetchone()
        if not row:
            return "failed"
        attempts, max_attempts = int(row[0]) + 1, int(row[1])
        if retryable and attempts < max_attempts:
            cur.execute(
                """UPDATE translation_jobs
                   SET status='pending', attempts=%s, cause=%s, error=%s, locked_by='', locked_at=NULL
                   WHERE id::text=%s""", (attempts, cause, str(error)[:2000], job_id))
            return "pending"
        cur.execute(
            """UPDATE translation_jobs
               SET status='failed', attempts=%s, cause=%s, error=%s, finished_at=now(), locked_by='', locked_at=NULL
               WHERE id::text=%s""", (attempts, cause, str(error)[:2000], job_id))
        return "failed"


def get_by_ids(job_ids: Iterable[str], *, user_id: Optional[str] = None) -> dict:
    """폴링 — job_id → {status, provider, cause, error, result}. user_id 지정 시 그 셀러 것만."""
    ids = [str(j) for j in (job_ids or []) if str(j).strip()]
    if not ids:
        return {}
    sql = ("SELECT id::text, status, provider, cause, error, result_json FROM translation_jobs "
           "WHERE id::text = ANY(%s) AND deleted_at IS NULL")
    params = [ids]
    if user_id is not None:
        sql += " AND user_id=%s"
        params.append(user_id)
    out = {}
    with pg.query() as cur:
        cur.execute(sql, params)
        for r in cur.fetchall():
            res = r[5]
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except ValueError:
                    res = {}
            out[r[0]] = {"status": r[1], "provider": r[2], "cause": r[3], "error": r[4],
                         "result": res or {}}
    return out


def counts() -> dict:
    """상태별 집계(진단)."""
    with pg.query() as cur:
        cur.execute("SELECT status, count(*) FROM translation_jobs WHERE deleted_at IS NULL GROUP BY status")
        return {r[0]: int(r[1]) for r in cur.fetchall()}
