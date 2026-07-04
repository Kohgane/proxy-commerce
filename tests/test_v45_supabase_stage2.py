"""tests/test_v45_supabase_stage2.py — 이관 2단계: market_links(연동정보·암호화 컬럼).

data/<seller>.json(Render ephemeral) → PG(영속). 값은 Fernet 암호문(enc_blob)에만.
검증: 저장→재시작→유지 / DB엔 암호문(평문 0) / 셀러 격리 / 삭제.
SUPABASE_DB_URL 설정 시에만 실행(미설정=data/ 파일 폴백, skip).
"""
from __future__ import annotations

import os

import pytest

_PG = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="SUPABASE_DB_URL 미설정 — PG 이관 테스트 skip")


@pytest.fixture
def pgclean(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("MARKET_CRED_ENC_KEY", Fernet.generate_key().decode())
    import src.db.pg as pg
    pg.reset_state()
    assert pg.pg_enabled()
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE market_links")
    yield pg
    pg.reset_state()


def test_save_get_persist_across_restart(pgclean):
    from src.seller_console import market_credentials as mc
    mc.save("u1", "coupang", {"COUPANG_ACCESS_KEY": "AK", "COUPANG_SECRET_KEY": "SK", "COUPANG_VENDOR_ID": "A1"})
    assert mc.get("u1", "coupang")["COUPANG_ACCESS_KEY"] == "AK"
    pgclean.reset_state()   # 재시작 시뮬
    got = mc.get("u1", "coupang")
    assert got["COUPANG_SECRET_KEY"] == "SK" and got["COUPANG_VENDOR_ID"] == "A1"


def test_db_stores_ciphertext_not_plaintext(pgclean):
    from src.seller_console import market_credentials as mc
    mc.save("u1", "coupang", {"COUPANG_SECRET_KEY": "TOPSECRET123"})
    with pgclean.query() as cur:
        cur.execute("SELECT enc_blob, is_encrypted FROM market_links WHERE user_id='u1' AND market='coupang'")
        blob, enc = cur.fetchone()
    assert enc is True
    assert "TOPSECRET123" not in blob          # 평문 노출 0
    assert blob.startswith("gAAAA")            # Fernet 암호문


def test_scope_isolation_and_delete(pgclean):
    from src.seller_console import market_credentials as mc
    mc.save("u1", "smartstore", {"NAVER_CLIENT_ID": "cid"})
    assert mc.get("u2", "smartstore") == {}    # 타 셀러 미노출
    assert mc.delete("u1", "smartstore") is True
    assert mc.get("u1", "smartstore") == {}


def test_merge_keeps_existing_fields(pgclean):
    from src.seller_console import market_credentials as mc
    mc.save("u1", "coupang", {"COUPANG_ACCESS_KEY": "AK", "COUPANG_SECRET_KEY": "SK"})
    mc.save("u1", "coupang", {"COUPANG_VENDOR_ID": "V1"})   # 일부만 갱신
    got = mc.get("u1", "coupang")
    assert got["COUPANG_ACCESS_KEY"] == "AK" and got["COUPANG_VENDOR_ID"] == "V1"


# ── 폴백(무-PG) 소스 계약 ───────────────────────────────────────────────────────
def test_fallback_contract_source():
    from pathlib import Path
    src = Path("src/seller_console/market_credentials.py").read_text(encoding="utf-8")
    assert "def _pg_links()" in src
    assert "def load_all_from_file(" in src        # 이관 스크립트용 파일 직접 로더
    assert "_b.save(seller_id, market, merged)" in src
    sch = Path("src/db/schema_stage2.sql").read_text(encoding="utf-8")
    assert "market_links" in sch and "enc_blob" in sch
