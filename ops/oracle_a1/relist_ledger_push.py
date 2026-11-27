#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELISTPUSH — 오너 11-27 11:51: 볼트 장부 요약(srv_snap/relist/<store>_ledger.txt · 블루호스트 RELISTLEDGER1127이 만든 것 · `.txt`, 내용은 JSON)을
운영 앱에 넘긴다. 오라클 kg-a1 = 운영 DB가 같은 기계 · 비밀값 옮기지 않음.

하는 쓰기는 **하나뿐**: `ops:oneshot:queue`에 `{op: relist_ledger_load, store, part, parts, src, rows}`를 덧붙인다
(오너가 허용한 운영 DB 쓰기 그대로 · 같은 조각이 줄에 있으면 안 넣음 · 행 잠금). 앱 10분 틱이 `relist:ledger:<store>`에 합치고
(허용 칸만 — 손님 정보·비밀값 칸은 앱이 버린다), 마지막 조각이 「목록 다시 만들기」(읽기만)를 건다.
사용: relist_ledger_push.py chezgoga            — 줄에 넣기
      relist_ledger_push.py chezgoga --dry      — 무엇을 넣을지 세기만
      relist_ledger_push.py chezgoga --read     — 앱 캐시 요약 읽기(READ ONLY)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

DB = "gogadb"
PER = 400
STORES = ("chezgoga", "gocosmos", "gogane")
KEEP = ("channel_no", "origin_no", "code", "cost", "currency", "url", "updated", "vault_reason", "vault_job", "cp_sold")
SQL = ("BEGIN; INSERT INTO app_state (key, value, updated_at) VALUES ('ops:oneshot:queue', '{}'::jsonb, now()) "
       "ON CONFLICT (key) DO NOTHING; "
       "SELECT 1 FROM app_state WHERE key='ops:oneshot:queue' FOR UPDATE; "
       "UPDATE app_state SET value = jsonb_set(value, '{rows}', COALESCE(value->'rows', '[]'::jsonb) || %(row)s::jsonb), "
       "updated_at = now() WHERE key='ops:oneshot:queue' AND NOT EXISTS ("
       "SELECT 1 FROM jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r "
       "WHERE r->>'op' = 'relist_ledger_load' AND r->>'item_id' = %(item)s); COMMIT;")
READ = ("BEGIN READ ONLY; SELECT jsonb_build_object('at', value->'at', 'keys', (SELECT count(*) FROM jsonb_object_keys(COALESCE(value->'rows', '{}'::jsonb))), "
        "'sources', value->'sources')::text FROM app_state WHERE key = %(key)s; "
        "SELECT count(*) FILTER (WHERE r->>'op' = 'relist_ledger_load')::text || ' 조각 줄에 남음' FROM app_state, "
        "jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r WHERE key = 'ops:oneshot:queue'; COMMIT;")


def _lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql: str) -> str:
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", DB, "-XtAq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


def chunks(doc: dict):
    """(src, part, parts, rows) — 허용 칸만 · 400줄씩."""
    out = []
    for src, rows in (doc.get("parts") or {}).items():
        if not re.match(r"^[a-z_]{2,30}$", str(src)):
            continue
        rows = [{k: r[k] for k in KEEP if k in r} for r in rows if isinstance(r, dict)]
        parts = max(1, (len(rows) + PER - 1) // PER)
        for i in range(parts):
            out.append((src, i + 1, parts, rows[i * PER:(i + 1) * PER]))
    return out


def queue_sql(store: str, at: str, ch, last: bool) -> str:
    src, part, parts, rows = ch
    item = f"{store}:{src}:{part}:{at}"
    row = {"op": "relist_ledger_load", "item_id": item, "store": store, "part": part, "parts": parts, "src": src, "rows": rows,
           "rebuild": bool(last), "why": "RELISTPUSH 볼트 장부 요약",
           "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return SQL % {"row": _lit(json.dumps(row, ensure_ascii=False)), "item": _lit(item)}


def main(argv):
    if not argv or argv[0] not in STORES:
        print(__doc__)
        return 2
    store = argv[0]
    if "--read" in argv:
        print(psql(READ % {"key": _lit("relist:ledger:" + store)}))
        return 0
    kg = os.environ.get("KG_HOME") or "/home1/ikymximy"
    path = ""
    for base in (os.path.join(kg, "vault"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")):
        for ext in ("txt", "json"):                                     # 블루호스트 볼트는 .json 을 안 올려 .txt(내용은 JSON)
            cand = os.path.join(base, "srv_snap", "relist", f"{store}_ledger.{ext}")
            if not path and os.path.exists(cand):
                path = cand
    try:
        doc = json.load(open(path))
    except Exception as e:                                             # noqa: BLE001
        print("요약 파일 못 읽음", type(e).__name__, "— 블루호스트 RELISTLEDGER1127 먼저")
        return 1
    at = str(doc.get("at") or "")[:19]
    cs = chunks(doc)
    print(store, "요약", at, "· 판매중지", doc.get("read"), "· 조각", len(cs), "·", {s: sum(len(c[3]) for c in cs if c[0] == s) for s in {c[0] for c in cs}})
    if "--dry" in argv:
        return 0
    for i, ch in enumerate(cs):
        out = psql(queue_sql(store, at, ch, i == len(cs) - 1))
        print(" ", ch[0], f"{ch[1]}/{ch[2]}", len(ch[3]), "줄 →", "줄에 넣음(같은 조각이면 그대로)" if not out.startswith("ERR") else out)
    print("📌 결과: RELISTPUSH", store, len(cs), "조각 — 앱 10분 틱이 합치고 목록을 다시 만들어요(읽기만)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
