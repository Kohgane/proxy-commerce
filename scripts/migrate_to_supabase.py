"""scripts/migrate_to_supabase.py — 이관 1단계: Google Sheets → Supabase Postgres.

버그 최다 테이블 2개(collect_history, user_tokens)를 Sheets에서 읽어 PG로 옮기고 건수 대조한다.
접속정보는 환경변수로만: GOOGLE_SHEET_ID(원본) + SUPABASE_DB_URL/DATABASE_URL(대상). 하드코딩 금지.

사용:
    GOOGLE_SHEET_ID=... SUPABASE_DB_URL=... python scripts/migrate_to_supabase.py          # 실행
    ... python scripts/migrate_to_supabase.py --count                                       # 건수만 대조(드라이런)

멱등: 이미 옮긴 행은 product_key 유니크/토큰 해시 유니크로 중복 삽입 0. 재실행 안전.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def _log(msg):
    print(msg, flush=True)


def _sheet_collect_rows():
    """Sheets collect_history 전체 행(dict)."""
    from src.seller_console import collect_history_store as ch
    if not ch._SHEET_ID:
        return []
    return list(ch._read_sheet_records())


def _sheet_token_rows():
    from src.auth import personal_tokens as pt
    if not pt._SHEET_ID:
        return []
    return list(pt._sheet_records())


def _pg():
    from src.db import pg
    if not pg.pg_enabled():
        raise SystemExit("SUPABASE_DB_URL/DATABASE_URL 미설정 또는 연결 실패 — 이관 대상 없음.")
    pg.init_schema()   # DDL은 직접 연결(5432)로
    return pg


def migrate_collect(cur, dry=False) -> tuple:
    """cur = 직접 연결(5432) 커서. 트랜잭션 풀러 이슈 회피."""
    rows = _sheet_collect_rows()
    from src.collectors.product_key import normalize_product_key
    inserted = 0
    for r in rows:
        if dry:
            continue
        url = r.get("url", "")
        pkey = normalize_product_key(url) or None
        collected_at = r.get("collected_at") or datetime.now(timezone.utc).isoformat()
        extra = r.get("extra_json") or "{}"
        try:
            extra_obj = json.loads(extra) if isinstance(extra, str) else (extra or {})
            if r.get("id"):
                extra_obj.setdefault("_legacy_id", str(r.get("id")))
            cur.execute(
                """INSERT INTO collect_history
                   (user_id, product_key, source, domain, url, title, image_url, price, currency, status, preview_url, extra_json, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                   ON CONFLICT (user_id, product_key)
                     WHERE product_key IS NOT NULL AND product_key <> '' AND deleted_at IS NULL
                   DO NOTHING""",
                (r.get("seller_id", ""), pkey, r.get("source", ""), r.get("domain", ""),
                 url, r.get("title", ""), r.get("image_url", ""), str(r.get("price", "") or ""),
                 r.get("currency", ""), r.get("status", "ok") or "ok", r.get("preview_url", ""),
                 json.dumps(extra_obj, ensure_ascii=False), collected_at))
            inserted += cur.rowcount
        except Exception as exc:
            _log(f"  collect 행 이관 실패(건너뜀): {exc}")
    cur.execute("SELECT count(*) FROM collect_history WHERE deleted_at IS NULL")
    return len(rows), inserted, int(cur.fetchone()[0])


def migrate_tokens(cur, dry=False) -> tuple:
    rows = _sheet_token_rows()
    inserted = 0
    for r in rows:
        if dry:
            continue
        try:
            scopes = json.loads(r.get("scopes_json", "[]") or "[]")
        except Exception:
            scopes = []
        revoked = str(r.get("revoked", "false")).lower() == "true"
        th = r.get("token_hash", "")
        if not th:
            continue
        try:
            cur.execute(
                """INSERT INTO user_tokens (user_id, token_hash, token_prefix, scopes, status, last_used_at, expires_at, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (token_hash) WHERE deleted_at IS NULL DO NOTHING""",
                (r.get("user_id", ""), th, th[:8], json.dumps(scopes),
                 "revoked" if revoked else "active",
                 r.get("last_used_at") or None, r.get("expires_at") or None,
                 r.get("created_at") or datetime.now(timezone.utc).isoformat()))
            inserted += cur.rowcount
        except Exception as exc:
            _log(f"  token 행 이관 실패(건너뜀): {exc}")
    cur.execute("SELECT count(*) FROM user_tokens WHERE deleted_at IS NULL")
    return len(rows), inserted, int(cur.fetchone()[0])


def migrate_market_links(cur, dry=False) -> tuple:
    """data/market_credentials/<seller>.json(Fernet) → market_links(암호문). 파일에서 직접 로드."""
    import glob
    import os as _os
    from src.seller_console import market_credentials as mc
    from src.db import market_links_pg as ml
    files = glob.glob(_os.path.join(mc._DATA_DIR, "*.json")) if _os.path.isdir(mc._DATA_DIR) else []
    sellers = 0
    inserted = 0
    for f in files:
        seller = _os.path.splitext(_os.path.basename(f))[0]
        creds = mc.load_all_from_file(seller)   # {market: {env:val}} — PG 활성이어도 파일 직접
        if not creds:
            continue
        sellers += 1
        if dry:
            continue
        for market, values in creds.items():
            enc_blob, is_enc = ml._encode(values)
            cur.execute(
                """INSERT INTO market_links (user_id, market, enc_blob, is_encrypted)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (user_id, market) WHERE deleted_at IS NULL
                   DO UPDATE SET enc_blob=EXCLUDED.enc_blob, is_encrypted=EXCLUDED.is_encrypted""",
                (seller, market, enc_blob, is_enc))
            inserted += 1
    cur.execute("SELECT count(*) FROM market_links WHERE deleted_at IS NULL")
    return sellers, inserted, int(cur.fetchone()[0])


def main():
    dry = "--count" in sys.argv
    pg = _pg()
    _log("=== 이관 1·2단계: Sheets/파일 → Supabase Postgres (직접 연결 5432) ===")
    # 마이그레이션은 직접 연결(5432)로 — 트랜잭션 풀러(6543)의 prepared/DDL 이슈 회피.
    with pg.direct_conn() as conn:
        with conn.cursor() as cur:
            sc, si, sp = migrate_collect(cur, dry=dry)
            tc, ti, tp = migrate_tokens(cur, dry=dry)
            mls, mli, mlp = migrate_market_links(cur, dry=dry)
    _log(f"[collect_history] Sheets 원본 {sc}건 · 삽입 {si}건 · PG 총 {sp}건")
    _log(f"[user_tokens]     Sheets 원본 {tc}건 · 삽입 {ti}건 · PG 총 {tp}건")
    _log(f"[market_links]    파일 셀러 {mls}명 · 삽입 {mli}건 · PG 총 {mlp}건")
    # 건수 대조(멱등 재실행 시 삽입 0이어도 PG 총계가 원본 이상이면 OK)
    ok = (sp >= sc) and (tp >= tc)
    _log(f"검증(건수 대조): collect PG≥Sheets={sp>=sc}, tokens PG≥Sheets={tp>=tc} → {'OK' if ok else '불일치'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    raise SystemExit(main())
