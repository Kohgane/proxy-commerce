#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DIAGRO — 오너 11-27 감독 1: 운영 진단을 CC가 스스로 읽는 길(오라클 kg-a1 · 운영 DB가 같은 기계 · 비밀값 옮기지 않음).

볼트 `scripts/ora/diagro.py`(이 파일 복사본)로 오라클 작업을 돌린다:
  ask NAME[:ARG] …   — `ops:oneshot:queue`에 `{op: diag_snapshot, item_id: "NAME:ARG"}`를 **덧붙인다**(오너가 허용한 운영 DB 쓰기 그대로 ·
                       같은 줄이 있으면 안 넣음 · 행 잠금). 앱 10분 틱이 계산해 `app_state diag:snap:NAME[:ARG]`에 적는다.
  read [NAME[:ARG]] … — `diag:snap:*`만 읽는다(READ ONLY 트랜잭션). 이름을 안 주면 진단 칸 목록(이름·시각·크기).
이 스크립트가 하는 쓰기는 `ask`의 덧붙이기 **하나뿐**(계약 `tests/test_owner1127_diag_export.py`). 다른 키·다른 표는 읽지도 않는다.
읽어 온 값은 앱이 이미 개인정보를 지운 것이지만, 여기서 한 번 더 전화·이메일·통관부호 꼴을 가린다.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

NAMES = ("restarts", "sources", "relist", "reenrich", "stores", "item", "prevalidate", "jobs", "blacklist", "taobao")
DB = "gogadb"
_SAFE_ARG = re.compile(r"^[A-Za-z0-9_.,|:\-]{0,120}$")
_PII = [re.compile(p) for p in (r"[\w.+-]+@[\w-]+\.[\w.-]+", r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)",
                                r"\+82[-\s]?\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}", r"(?<![A-Z0-9])P\d{12}(?![0-9])")]

ASK_SQL = ("BEGIN; INSERT INTO app_state (key, value, updated_at) VALUES ('ops:oneshot:queue', '{}'::jsonb, now()) "
           "ON CONFLICT (key) DO NOTHING; "
           "SELECT 1 FROM app_state WHERE key='ops:oneshot:queue' FOR UPDATE; "
           "UPDATE app_state SET value = jsonb_set(value, '{rows}', COALESCE(value->'rows', '[]'::jsonb) || %(row)s::jsonb), "
           "updated_at = now() WHERE key='ops:oneshot:queue' AND NOT EXISTS ("
           "SELECT 1 FROM jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r "
           "WHERE r->>'op' = 'diag_snapshot' AND r->>'item_id' = %(item)s); COMMIT;")
READ_SQL = "BEGIN READ ONLY; SELECT value::text FROM app_state WHERE key = %(key)s; COMMIT;"
LIST_SQL = ("BEGIN READ ONLY; SELECT key || ' ' || updated_at::text || ' ' || length(value::text) FROM app_state "
            "WHERE key LIKE 'diag:snap:%%' ORDER BY updated_at DESC LIMIT 50; COMMIT;")


def _lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def parse(spec: str):
    name, _, arg = str(spec or "").partition(":")
    if name not in NAMES or not _SAFE_ARG.match(arg):
        raise SystemExit(f"모르는 진단이거나 인자 꼴이 아니에요: {spec!r}")
    return name, arg


def ask_sql(spec: str) -> str:
    name, arg = parse(spec)
    item = f"{name}:{arg}"
    row = json.dumps({"op": "diag_snapshot", "item_id": item, "why": "CC 진단(diagro)",
                      "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, ensure_ascii=False)
    return ASK_SQL % {"row": _lit(row), "item": _lit(item)}


def read_sql(spec: str) -> str:
    name, arg = parse(spec)
    return READ_SQL % {"key": _lit("diag:snap:" + name + ((":" + arg) if arg else ""))}


def mask(s: str) -> str:
    for rx in _PII:
        s = rx.sub("<가림>", s)
    return s


def psql(sql: str) -> str:
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", DB, "-XtAq", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


def main(argv):
    if not argv or argv[0] not in ("ask", "read"):
        print(__doc__)
        return 2
    cmd, specs = argv[0], argv[1:]
    if cmd == "ask":
        for sp in specs:
            out = psql(ask_sql(sp))
            print("ask", sp, "→", "줄에 넣음(같은 줄이 있으면 그대로)" if not out.startswith("ERR") else out)
        return 0
    if not specs:
        print(mask(psql(LIST_SQL)))
        return 0
    for sp in specs:
        t = psql(read_sql(sp))
        print(f"== {sp}")
        if not t or t.startswith("ERR"):
            print(t or "(아직 없음 — ask 뒤 10분 틱을 기다려요)")
            continue
        try:
            print(mask(json.dumps(json.loads(t), ensure_ascii=False, indent=1)))
        except Exception:
            print(mask(t[:20000]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
