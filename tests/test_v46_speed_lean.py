"""tests/test_v46_speed_lean.py — v46 STEP1: 목록 대형 컬럼 제외(lean) + summary/distinct SQL 위임.

병목 실측(로컬 PG, 2000행·extra_json 40이미지): summary 438ms + distinct 437ms(전체 행 detoast)
가 지배 → 목록 871ms. 수리: 스토어 summary/distinct를 PG SQL 집계로 위임(전체 파이썬 스캔 폐지) +
목록 list_items는 lean projection(대형 배열 제외, 대표 썸네일 image_url + 첫 이미지 1장만). → 27ms(32×).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

CHS = Path("src/seller_console/collect_history_store.py").read_text(encoding="utf-8")
CHPG = Path("src/db/collect_history_pg.py").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


def test_summary_distinct_delegate_to_pg():
    # 스토어 summary/distinct가 PG면 SQL 집계로 위임(전체 행 list_items 스캔 금지)
    seg_s = CHS[CHS.index("def summary("):CHS.index("def distinct_domains(")]
    assert "_b.summary(" in seg_s
    seg_d = CHS[CHS.index("def distinct_domains("):]
    assert "_b.distinct_domains(" in seg_d


def test_list_lean_projection_excludes_big_columns():
    # PG lean projection: 대형 컬럼(extra_json 이미지배열·상세·리뷰) 제외한 축약 jsonb
    assert "_SELECT_LEAN" in CHPG and "_LEAN_EXTRA" in CHPG
    assert "jsonb_build_object" in CHPG
    assert "def list_items" in CHPG and "lean=False" in CHPG
    # 뷰가 목록에서 lean=True 사용
    assert "lean=True" in VIEWS


@pytest.fixture(autouse=True)
def _mem():
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


def test_lean_keeps_thumb_drops_arrays_inmemory():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    ch.append(source="extension", url="https://a.com/g-1", title="상품", seller_id="u1",
              image="https://a.com/rep.jpg",
              extra={"title_en": "item", "images": ["https://a.com/rep.jpg"] + [f"https://a.com/{i}.jpg" for i in range(40)],
                     "description": "x" * 5000, "reviews": [{"text": "r"}] * 10, "detail_specs": [{"k": "a", "v": "b"}] * 30})
    lean = ch.list_items(seller_ids={"u1"}, limit=50, lean=True)
    ex = json.loads(lean[0]["extra_json"])
    assert lean[0]["image_url"] == "https://a.com/rep.jpg"          # 대표 썸네일 유지
    assert ex.get("title_en") == "item"                            # 언어 토글용 소필드 유지
    assert len(ex.get("images", [])) == 1                          # 첫 1장만(40장 배열 제외)
    assert "description" not in ex and "reviews" not in ex and "detail_specs" not in ex   # 대형 제외
    # full은 여전히 전체
    full = ch.list_items(seller_ids={"u1"}, limit=50, lean=False)
    fex = json.loads(full[0]["extra_json"])
    assert len(fex.get("images", [])) == 41 and "description" in fex


def test_summary_values_correct_inmemory():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    for i in range(3):
        ch.append(source="extension", url=f"https://a.com/g-{i}", title=f"t{i}", seller_id="u1")
    ch.append(source="bookmarklet", url="https://b.com/g", title="x", seller_id="u1")
    s = ch.summary(days=30, seller_ids={"u1"})
    assert s["total"] == 4 and s["domains"] == 2
    assert s["by_source"]["extension"] == 3 and s["by_source"]["bookmarklet"] == 1
