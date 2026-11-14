#!/usr/bin/env bash
# ops/oracle_a1/rehearse_schema_from_repo.sh — Supabase에 안 닿아도(402) 되는 스키마 리허설.
#
# 앱이 부팅 때 적용하는 것과 같은 파일(src/db/schema_stage*.sql, pg.SCHEMA_FILES 순서)을 A1 DB에 psql로 적용하고
# 표·칸 목록을 찍는다. 운영 public과의 대조표(22표)는 README 「로컬 리허설 기록」. 데이터는 11/19 `migrate_from_supabase.sh MODE=data`.
#   DST_URL_FILE=<A1 연결 문자열 한 줄 파일> REPO=<proxy-commerce 체크아웃> bash rehearse_schema_from_repo.sh
set -euo pipefail
: "${DST_URL_FILE:?DST_URL_FILE 필요}"; : "${REPO:?REPO(저장소 경로) 필요}"
DST="$(head -n1 "$DST_URL_FILE")"
FILES="$(python3 -c "import ast,sys
src=open(sys.argv[1],encoding='utf-8').read()
t=ast.parse(src)
for n in ast.walk(t):
    if isinstance(n,ast.Assign) and any(getattr(x,'id','')=='SCHEMA_FILES' for x in n.targets):
        print(' '.join(e.value for e in n.value.elts))" "$REPO/src/db/pg.py")"
[ -n "$FILES" ] || { echo "SCHEMA_FILES를 못 읽음"; exit 1; }
psql "$DST" -v ON_ERROR_STOP=1 -q -c 'CREATE EXTENSION IF NOT EXISTS pgcrypto' -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'
for f in $FILES; do
  psql "$DST" -v ON_ERROR_STOP=1 -q -f "$REPO/src/db/$f" >/dev/null && echo "적용 $f"
done
psql "$DST" -At -c "select count(*) from pg_tables where schemaname='public'" | sed 's/^/public 표 수: /'
psql "$DST" -At -c "select count(*) from pg_indexes where schemaname='public'" | sed 's/^/public 인덱스 수: /'
echo "끝 — 운영에만 있는 checklist 표는 데이터 덤프(MODE=data)가 옮긴다."
