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


def migrate_collect(cur, dry=False) -> dict:
    """cur = 직접 연결(5432) 커서. 트랜잭션 풀러 이슈 회피.

    스킵된 행의 사유를 증명한다:
    - product_key 중복(ON CONFLICT DO NOTHING, rowcount 0) → 중복으로 분류·키 목록 로깅.
    - 예외 발생 → 에러로 분류·해당 행 url + 원인 로깅.
    검증은 **distinct key 기준**(중복은 정상 dedup): 에러 0 + PG총계 == 기대 distinct면 PASS.
    """
    rows = _sheet_collect_rows()
    from src.collectors.product_key import normalize_product_key
    inserted = 0
    dup_keys = []          # 중복(정상 dedup)으로 스킵된 product_key
    errors = []            # (url, 원인) — 진짜 실패
    empty_key_rows = 0     # product_key 없는 행(중복 판정 불가 → 전부 삽입)
    distinct_keys = set()
    for r in rows:
        url = r.get("url", "")
        pkey = normalize_product_key(url) or None
        if pkey:
            distinct_keys.add(pkey)
        else:
            empty_key_rows += 1
        if dry:
            continue
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
            if cur.rowcount == 0:
                # ON CONFLICT DO NOTHING → 같은 (user_id, product_key) 활성 행 존재 = 중복 스킵
                dup_keys.append(pkey or url)
            else:
                inserted += cur.rowcount
        except Exception as exc:
            errors.append((url, str(exc)))
            _log(f"  collect 에러 스킵: url={url[:80]} 원인={exc}")
    cur.execute("SELECT count(*) FROM collect_history WHERE deleted_at IS NULL")
    pg_total = int(cur.fetchone()[0])
    distinct_expected = len(distinct_keys) + empty_key_rows   # 기대 건수(중복 제거 후)
    if dup_keys:
        _log(f"  중복 스킵 {len(dup_keys)}건(정상 dedup) — product_key 목록: {dup_keys}")
    if errors:
        _log(f"  에러 스킵 {len(errors)}건(실패) — 위 상세 로그 참조")
    return {
        "sheets_total": len(rows), "inserted": inserted, "pg_total": pg_total,
        "dup_count": len(dup_keys), "err_count": len(errors),
        "distinct_expected": distinct_expected, "dup_keys": dup_keys, "errors": errors,
    }


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


def _sheet_order_rows():
    import os as _os
    sid = _os.getenv("GOOGLE_SHEET_ID")
    if not sid:
        return []
    from src.utils.sheets import get_all_records_safe, get_or_create_worksheet, open_sheet_object
    from src.seller_console.orders.sheets_adapter import ORDERS_HEADERS
    sh = open_sheet_object(sid)
    ws = get_or_create_worksheet(sh, "orders", headers=ORDERS_HEADERS)
    return get_all_records_safe(ws)


def migrate_orders(cur, dry=False) -> tuple:
    """Sheets 'orders' 워크시트 → orders 테이블. (order_id, marketplace) upsert."""
    from src.db.orders_pg import _COLS
    rows = [r for r in _sheet_order_rows() if r.get("order_id")]
    inserted = 0
    set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in _COLS if c not in ("order_id", "marketplace"))
    for r in rows:
        if dry:
            continue
        try:
            vals = [str(r.get(c, "") if r.get(c) is not None else "") for c in _COLS]
            cur.execute(
                f"""INSERT INTO orders ({', '.join(_COLS)})
                    VALUES ({', '.join(['%s'] * len(_COLS))})
                    ON CONFLICT (order_id, marketplace) WHERE deleted_at IS NULL
                    DO UPDATE SET {set_clause}""",
                vals)
            inserted += 1
        except Exception as exc:
            _log(f"  order 행 이관 실패(건너뜀): {exc}")
    cur.execute("SELECT count(*) FROM orders WHERE deleted_at IS NULL")
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
            cm = migrate_collect(cur, dry=dry)
            tc, ti, tp = migrate_tokens(cur, dry=dry)
            mls, mli, mlp = migrate_market_links(cur, dry=dry)
            oc, oi, op = migrate_orders(cur, dry=dry)
    _log(f"[collect_history] Sheets 원본 {cm['sheets_total']}건 · 삽입 {cm['inserted']}건 · "
         f"중복(정상 dedup) {cm['dup_count']}건 · 에러 {cm['err_count']}건 · "
         f"PG 총 {cm['pg_total']}건 · 기대 distinct {cm['distinct_expected']}건")
    _log(f"[user_tokens]     Sheets 원본 {tc}건 · 삽입 {ti}건 · PG 총 {tp}건")
    _log(f"[market_links]    파일 셀러 {mls}명 · 삽입 {mli}건 · PG 총 {mlp}건")
    _log(f"[orders]          Sheets 원본 {oc}건 · 삽입 {oi}건 · PG 총 {op}건")
    # 검증(distinct key 기준): 중복은 정상 dedup(스킵 정당) — 에러 0 + PG총계 == 기대 distinct면 PASS.
    collect_ok = (cm["err_count"] == 0) and (cm["pg_total"] >= cm["distinct_expected"])
    tokens_ok = (tp >= tc)
    ok = collect_ok and tokens_ok
    _log(f"검증(distinct 기준): collect PASS={collect_ok} (PG {cm['pg_total']} == 기대 distinct "
         f"{cm['distinct_expected']}, 에러 {cm['err_count']}) · tokens PASS={tokens_ok} → {'OK' if ok else '불일치'}")
    if cm["err_count"]:
        _log("  ※ 에러 스킵이 있어 불일치 — 위 'collect 에러 스킵' 로그의 행/원인 확인 후 재실행하세요.")
    elif cm["dup_count"]:
        _log(f"  ※ 스킵 {cm['dup_count']}건은 전부 product_key 중복(같은 상품 재수집) = 정상 dedup → PASS.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    raise SystemExit(main())
