"""src/db/image_translate_usage_pg.py — 이미지 번역 사용량·벤치 저장소 (D1).

PG가 켜져 있으면 `image_translate_usage`·`image_bench_runs`, 아니면 **인메모리**(개발·테스트).

**카운터를 따로 두지 않는다** — 호출을 행으로 남기고 집계는 더해서 낸다.
카운터와 실제가 갈리면 어느 쪽이 맞는지 알 수 없게 된다(D0-6).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.db import pg

logger = logging.getLogger(__name__)

_MEM_USAGE: list = []
_MEM_RUNS: dict = {}


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM_USAGE.clear()
    _MEM_RUNS.clear()


# ---------------------------------------------------------------------------
# 사용량
# ---------------------------------------------------------------------------

def add(user_id: str, *, vendor: str = "tencent", pages: int = 0,
        ok_pages: int = 0, ms: int = 0) -> bool:
    uid = str(user_id or "")
    row = {"user_id": uid, "vendor": vendor, "pages": int(pages),
           "ok_pages": int(ok_pages), "ms": int(ms),
           "created_at": datetime.now(timezone.utc)}
    if not _enabled():
        _MEM_USAGE.append(row)
        return True
    with pg.tx() as cur:
        cur.execute(
            "INSERT INTO image_translate_usage (user_id, vendor, pages, ok_pages, ms) "
            "VALUES (%s, %s, %s, %s, %s)",
            (uid, vendor, int(pages), int(ok_pages), int(ms)))
    return True


def daily_totals(days: int = 14) -> list:
    """관리자 화면용 **일 합계** — `[{day, user_id, calls, pages, ok_pages, ms}]`."""
    if not _enabled():
        agg: dict = {}
        for r in _MEM_USAGE:
            key = (r["created_at"].date().isoformat(), r["user_id"])
            a = agg.setdefault(key, {"day": key[0], "user_id": key[1], "calls": 0,
                                     "pages": 0, "ok_pages": 0, "ms": 0})
            a["calls"] += 1
            for k in ("pages", "ok_pages", "ms"):
                a[k] += int(r.get(k) or 0)
        return sorted(agg.values(), key=lambda x: (x["day"], x["user_id"]), reverse=True)
    with pg.query() as cur:
        cur.execute(
            "SELECT to_char(created_at::date, 'YYYY-MM-DD') AS day, user_id, count(*) AS calls, "
            "       coalesce(sum(pages),0), coalesce(sum(ok_pages),0), coalesce(sum(ms),0) "
            "FROM image_translate_usage "
            "WHERE created_at >= now() - (%s || ' days')::interval "
            "GROUP BY 1, 2 ORDER BY 1 DESC, 2", (int(days),))
        return [{"day": r[0], "user_id": r[1], "calls": int(r[2]),
                 "pages": int(r[3]), "ok_pages": int(r[4]), "ms": int(r[5])}
                for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# 벤치 실행 · 채점
# ---------------------------------------------------------------------------

def save_run(run_id: str, user_id: str, results: list, *, vendor: str = "tencent",
             note: str = "") -> bool:
    rid = str(run_id or "").strip()
    if not rid:
        return False
    if not _enabled():
        _MEM_RUNS[rid] = {"run_id": rid, "user_id": user_id, "vendor": vendor,
                          "results": results, "scores": _MEM_RUNS.get(rid, {}).get("scores", {}),
                          "note": note, "created_at": datetime.now(timezone.utc).isoformat()}
        return True
    with pg.tx() as cur:
        cur.execute(
            "INSERT INTO image_bench_runs (run_id, user_id, vendor, results, note) "
            "VALUES (%s, %s, %s, %s::jsonb, %s) "
            "ON CONFLICT (run_id) DO UPDATE SET results = EXCLUDED.results, note = EXCLUDED.note",
            (rid, str(user_id or ""), vendor, json.dumps(results, ensure_ascii=False), note))
    return True


def save_scores(run_id: str, scores: dict) -> bool:
    """오너가 매긴 5축 점수. **사람이 매긴 값이라 파일이 아니라 여기 둔다** — 배포로 사라지면 안 된다."""
    rid = str(run_id or "").strip()
    if not rid:
        return False
    if not _enabled():
        row = _MEM_RUNS.setdefault(rid, {"run_id": rid, "results": [], "scores": {}})
        row["scores"] = scores
        return True
    with pg.tx() as cur:
        cur.execute("UPDATE image_bench_runs SET scores = %s::jsonb WHERE run_id = %s",
                    (json.dumps(scores, ensure_ascii=False), rid))
        return bool(cur.rowcount)


def get_run(run_id: str) -> dict:
    rid = str(run_id or "").strip()
    if not rid:
        return {}
    if not _enabled():
        return dict(_MEM_RUNS.get(rid, {}))
    with pg.query() as cur:
        cur.execute("SELECT run_id, user_id, vendor, results, scores, note, created_at "
                    "FROM image_bench_runs WHERE run_id = %s", (rid,))
        r = cur.fetchone()
    if not r:
        return {}
    return {"run_id": r[0], "user_id": r[1], "vendor": r[2],
            "results": r[3] if isinstance(r[3], list) else json.loads(r[3] or "[]"),
            "scores": r[4] if isinstance(r[4], dict) else json.loads(r[4] or "{}"),
            "note": r[5], "created_at": r[6].isoformat() if r[6] else ""}


def list_runs(limit: int = 20) -> list:
    """최근 실행 목록(재실행 비교용) — `[{run_id, created_at, pages, ok, scored}]`."""
    if not _enabled():
        rows = sorted(_MEM_RUNS.values(), key=lambda x: x.get("created_at", ""), reverse=True)
    else:
        with pg.query() as cur:
            cur.execute("SELECT run_id, created_at, results, scores FROM image_bench_runs "
                        "ORDER BY created_at DESC LIMIT %s", (int(limit),))
            rows = [{"run_id": r[0], "created_at": r[1].isoformat() if r[1] else "",
                     "results": r[2] if isinstance(r[2], list) else json.loads(r[2] or "[]"),
                     "scores": r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}")}
                    for r in cur.fetchall()]
    out = []
    for r in rows[:limit]:
        res = r.get("results") or []
        out.append({"run_id": r.get("run_id", ""), "created_at": r.get("created_at", ""),
                    "pages": len(res),
                    "ok": sum(1 for x in res if isinstance(x, dict) and x.get("status") == "done"),
                    "scored": bool(r.get("scores"))})
    return out
