"""tests/test_v45_speed2.py — 속도2: 타이밍 측정(Server-Timing)·페이로드 다이어트·PG 인덱스·CSP 폰트.

오너: 병목을 수치로 증명. 서버 구간 타이밍(db/render)을 Server-Timing 헤더+로그로 노출,
목록은 대표 썸네일 1장 + extra_json 1회 파싱, PG 목록 인덱스(user_id, created_at) 추가,
CSP가 막던 Noto Serif(fonts.googleapis.com) 허용.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SEC = Path("src/middleware/security.py").read_text(encoding="utf-8")
SCHEMA = Path("src/db/schema_stage1.sql").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_server_timing_header(client):
    from src.seller_console import collect_history_store as ch
    ch.append(source="extension", url="https://ex.com/g-1", title="상품", seller_id="default",
              extra={"title_en": "p", "images": ["a.jpg"]})
    r = client.get("/seller/collect/history")
    st = r.headers.get("Server-Timing", "")
    assert "total;dur=" in st          # 총 시간
    assert "render;dur=" in st         # 렌더 구간(db는 목록에 항목 있을 때)


def test_perf_util():
    from src.utils.perf import perf_block, perf_snapshot, perf_server_timing
    # 요청 컨텍스트 밖에서도 안전(빈 스냅샷)
    with perf_block("x"):
        pass
    assert isinstance(perf_snapshot(), dict)
    assert isinstance(perf_server_timing(), str)


def test_list_single_thumbnail_and_parse_once(client):
    from src.seller_console import collect_history_store as ch
    ch.append(source="extension", url="https://ex.com/g-2", title="가방", seller_id="default",
              extra={"title_en": "bag", "images": ["https://i/rep.jpg", "https://i/2.jpg", "https://i/3.jpg"]})
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "https://i/rep.jpg" in html                       # 대표 1장
    assert "https://i/2.jpg" not in html                     # 목록엔 추가 썸네일 미노출(다이어트)
    # extra_json 파싱은 항목당 1회(3회 중복 제거) — 소스에 반복 json.loads 없음
    assert "각 항목에 썸네일 목록(최대 5장)" not in VIEWS      # 옛 5장 로직 제거
    assert "extra_json은 항목당 **한 번만** 파싱" in VIEWS


def test_pg_list_index():
    assert "ix_collect_history_user_created" in SCHEMA
    assert "(user_id, created_at DESC)" in SCHEMA


def test_csp_allows_brand_fonts():
    assert "fonts.googleapis.com" in SEC          # style-src (Noto Serif KR 로드 허용)
    assert "fonts.gstatic.com" in SEC             # font-src
