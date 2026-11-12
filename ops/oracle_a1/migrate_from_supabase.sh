#!/usr/bin/env bash
# ops/oracle_a1/migrate_from_supabase.sh — Supabase(원본) → A1(새 DB) 덤프·복원·표별 건수 대조.
#
# 연결 문자열은 **파일**에서 읽는다(명령줄·셸 기록·로그에 비밀번호를 남기지 않게):
#   SRC_URL_FILE  = Supabase DATABASE_URL_DIRECT 값 한 줄(직접 연결 5432) — 600 권한
#   DST_URL_FILE  = A1 연결 문자열 한 줄(sslmode=require) — 600 권한
# 모드:
#   MODE=schema  스키마만(리허설 · 402로 데이터가 막혀도 된다) — 기본
#   MODE=data    스키마 + 데이터(11/19 풀리는 즉시) · 끝에 표별 건수 대조표
# 원본엔 쓰지 않는다(pg_dump는 읽기만). 대상 DB의 public 스키마는 비우고 다시 만든다(A1 전용 DB).
set -euo pipefail
MODE="${MODE:-schema}"
: "${SRC_URL_FILE:?SRC_URL_FILE 필요}"; : "${DST_URL_FILE:?DST_URL_FILE 필요}"
SRC="$(head -n1 "$SRC_URL_FILE")"; DST="$(head -n1 "$DST_URL_FILE")"
OUT_DIR="${OUT_DIR:-/var/backups/kgp/migrate}"; mkdir -p "$OUT_DIR"; chmod 700 "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$OUT_DIR/supabase_${MODE}_${STAMP}.dump"

ARGS=(--format=custom --no-owner --no-acl --schema=public --file="$DUMP")
[ "$MODE" = schema ] && ARGS+=(--schema-only)
echo "== 덤프($MODE) → $DUMP"
pg_dump "${ARGS[@]}" "$SRC"
echo "   크기 $(du -h "$DUMP" | cut -f1)"

echo "== 복원 → 대상(대상 public 스키마를 비우고 다시 — A1 전용 DB라 괜찮다)"
psql "$DST" -v ON_ERROR_STOP=1 -q -c 'DROP SCHEMA IF EXISTS public CASCADE' -c 'CREATE SCHEMA public' \
  -c 'CREATE EXTENSION IF NOT EXISTS pgcrypto' -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'
LIST="$DUMP.list"
pg_restore --list "$DUMP" | grep -v ' SCHEMA - public ' | grep -v ' EXTENSION ' | grep -v ' COMMENT - EXTENSION ' > "$LIST"
pg_restore --no-owner --no-acl --exit-on-error --use-list="$LIST" -d "$DST" "$DUMP"

echo "== 대조(표 이름 · 원본 · 대상)"
TABLES="$(psql "$DST" -At -c "select tablename from pg_tables where schemaname='public' order by 1")"
fail=0
for t in $TABLES; do
  s="$(psql "$SRC" -At -c "select count(*) from public.\"$t\"" 2>/dev/null || echo '?')"
  d="$(psql "$DST" -At -c "select count(*) from public.\"$t\"")"
  mark="="; [ "$s" = "$d" ] || { mark="≠"; [ "$MODE" = data ] && fail=1; }
  printf '%-26s %8s %s %8s\n' "$t" "$s" "$mark" "$d"
done
src_idx="$(psql "$SRC" -At -c "select count(*) from pg_indexes where schemaname='public'")"
dst_idx="$(psql "$DST" -At -c "select count(*) from pg_indexes where schemaname='public'")"
echo "인덱스: 원본 $src_idx · 대상 $dst_idx"
[ "$MODE" = data ] && { [ $fail = 0 ] && echo "건수 전부 같음 ✔" || { echo "건수 다름 — 전환하지 말 것"; exit 2; }; }
echo "끝($MODE)."
