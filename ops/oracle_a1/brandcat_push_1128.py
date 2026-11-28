#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BRANDCATPUSH1128 — 블루호스트 BRANDCAT1128 결과(볼트 srv_snap/apply_out/brandcat_data_<store>.txt)를 앱 큐에.
쓰기는 `ops:oneshot:queue`에 `relist_ledger_load` 덧붙이기 하나뿐(허용된 운영 DB 쓰기). 품번 일치 → src=code_match(「품번 일치(공식몰)」 · 실측처럼 본다) ·
이름 일치 → src=name_match(「이름 일치(확인 필요)」 · 저절로 안 켬). 마지막 조각에 --rebuild면 목록 다시 만들기(읽기만).
사용: brandcat_push_1128.py chezgoga [--dry] [--rebuild]"""
import json, os, subprocess, sys
from datetime import datetime, timezone
SQL = ("BEGIN; INSERT INTO app_state (key, value, updated_at) VALUES ('ops:oneshot:queue', '{}'::jsonb, now()) "
       "ON CONFLICT (key) DO NOTHING; SELECT 1 FROM app_state WHERE key='ops:oneshot:queue' FOR UPDATE; "
       "UPDATE app_state SET value = jsonb_set(value, '{rows}', COALESCE(value->'rows', '[]'::jsonb) || %(row)s::jsonb), "
       "updated_at = now() WHERE key='ops:oneshot:queue' AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r "
       "WHERE r->>'op' = 'relist_ledger_load' AND r->>'item_id' = %(item)s); COMMIT;")
KEEP = ("channel_no", "origin_no", "code", "cost", "currency", "url", "updated", "src_state", "via")


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql):
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "gogadb", "-XtAq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


def main(argv):
    store = argv[0] if argv else "chezgoga"
    kg = os.environ.get("KG_HOME") or "/home1/ikymximy"
    f = os.path.join(kg, "vault", "srv_snap", "apply_out", f"brandcat_data_{store}.txt")
    if not os.path.exists(f):
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "srv_snap", "apply_out", f"brandcat_data_{store}.txt")
    doc = json.load(open(f))
    groups = {"code_match": [], "name_match": []}
    for r in doc.get("rows") or []:
        groups["code_match" if r.get("kind") == "code" else "name_match"].append({k: r[k] for k in KEEP if k in r})
    print(store, "블루호스트 결과", doc.get("at"), {k: len(v) for k, v in groups.items()})
    if "--dry" in argv:
        return 0
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    srcs = [s for s in groups if groups[s]]
    for i, src in enumerate(srcs):
        item = f"{store}:{src}:1:{at}"
        row = {"op": "relist_ledger_load", "item_id": item, "store": store, "part": 1, "parts": 1, "src": src, "rows": groups[src],
               "rebuild": i == len(srcs) - 1 and "--rebuild" in argv, "why": "BRANDCAT1128 공식몰 전체 목록",
               "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        res = psql(SQL % {"row": _lit(json.dumps(row, ensure_ascii=False)), "item": _lit(item)})
        print(" ", src, len(groups[src]), "줄 →", "줄에 넣음" if not res.startswith("ERR") else res)
    print("📌 결과: BRANDCATPUSH1128", store)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
