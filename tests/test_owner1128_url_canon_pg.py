"""오너 11-28 감독 5 — 짧은 링크 → 정본 주소 고쳐 쓰기의 PG 경로(`collect_history_pg.set_source_url`).
원래 주소는 raw_url 열(비어 있을 때만)·extra_json.raw_url에 보존 · 상품 키·도메인 같이 · 같은 상품이 다른 행에 있으면 안 바꿈.
DATABASE_URL(테스트용 PG) 설정 시에만 실행 — CI pg-suite 레인."""
from __future__ import annotations

import json
import os

import pytest

_PG = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 테스트 skip")


@pytest.fixture
def pgclean():
    import src.db.pg as pg
    pg.reset_state()
    assert pg.pg_enabled(), "PG 연결 실패"
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE collect_history")
    yield pg
    pg.reset_state()


def test_set_source_url_keeps_raw_url_and_refuses_duplicate_product(pgclean):
    from src.seller_console import collect_history_store as ch
    a = ch.append(source="extension", url="https://a.co/d/00RG5ThB", title="OKNIFE", seller_id="u1", extra={"images": []})
    b = ch.append(source="extension", url="https://www.amazon.com/dp/B0OTHER123", title="tomtoc", seller_id="u1")
    c = ch.append(source="extension", url="https://a.co/d/11XYZ", title="같은 상품 다른 짧은 링크", seller_id="u1")
    out = ch.set_source_url(a, "https://www.amazon.com/dp/B0CXYZ1234", raw_url="https://a.co/d/00RG5ThB", seller_ids={"u1"})
    assert out == {"ok": True}
    row = ch.get(a, seller_ids={"u1"})
    assert row["url"] == "https://www.amazon.com/dp/B0CXYZ1234" and row["domain"] == "www.amazon.com"
    assert json.loads(row["extra_json"] if isinstance(row["extra_json"], str) else json.dumps(row["extra_json"]))["raw_url"] == "https://a.co/d/00RG5ThB"
    with pgclean.tx() as cur:
        cur.execute("SELECT raw_url, product_key FROM collect_history WHERE id::text=%s", [a])
        raw, key = cur.fetchone()
    assert raw == "https://a.co/d/00RG5ThB" and "B0CXYZ1234" in (key or "")
    # 다른 범위(셀러)면 안 바뀜
    assert ch.set_source_url(b, "https://www.amazon.com/dp/B0ZZZ", raw_url="x", seller_ids={"someone"}) == {"ok": False}
    # 같은 상품이 이미 있으면 안 바꿈(상품 키 겹침)
    dup = ch.set_source_url(c, "https://www.amazon.com/dp/B0CXYZ1234", raw_url="https://a.co/d/11XYZ", seller_ids={"u1"})
    assert dup["ok"] is False and "겹침" in dup["why"]
    assert ch.get(c, seller_ids={"u1"})["url"] == "https://a.co/d/11XYZ"
