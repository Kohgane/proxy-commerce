"""tests/test_v45_speed_infinite.py — 속도: 첫50 + 무한스크롤 + 나이아 서버버킷 lazy-fetch.

이름순 전체 5000 로드 폐기. 카탈로그·수집이력 모두 첫 per_page개만 렌더 + fmt=rows로 이어붙임.
나이아 점프는 서버가 준 버킷(count/offset/sample)으로 해당 섹션만 lazy-fetch(5000행 미렌더).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
JS = Path("src/seller_console/static/kgp-fastscroll.js").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_no_full_5000_load():
    # 전체 5000 로드 폐기 — all_items[:_FASTSCROLL_MAX] 슬라이스가 뷰에서 사라져야 한다.
    assert "all_items[:_FASTSCROLL_MAX]" not in VIEWS
    assert "items[:_FASTSCROLL_MAX]" not in VIEWS
    # 공통 창(offset~per_page)
    assert "all_items[offset:offset + per_page]" in VIEWS
    assert "all_rows[offset:offset + per_page]" in VIEWS


def test_bucket_helper():
    from src.seller_console.views import _fs_bucket_of, _fs_build_buckets
    assert _fs_bucket_of("숄더 팩") == "ㅅ"
    assert _fs_bucket_of("Nike") == "N"
    assert _fs_bucket_of("123") == "#"
    pairs = sorted([("가방", ""), ("사과", ""), ("Nike", ""), ("가위", "")], key=lambda p: p[0].lower())
    bk = _fs_build_buckets(pairs)
    assert bk["ㄱ"]["count"] == 2 and "offset" in bk["ㄱ"] and bk["ㄱ"]["sample"]
    assert bk["ㅅ"]["count"] == 1 and bk["N"]["count"] == 1


def test_history_first_page_and_fragment(client):
    from src.seller_console import collect_history_store as ch
    for i in range(60):
        ch.append(source="extension", url=f"https://ex.com/g-{i}", title=f"상품{i:02d}",
                  seller_id="default", extra={"title_en": f"item{i}"})
    full = client.get("/seller/collect/history?sort=title").get_data(as_text=True)
    # 첫 페이지는 50건만(60이 아니라) + 무한스크롤 메타 + 나이아 버킷 init
    assert full.count("kgp-open-drawer btn btn-success") == 50
    assert 'id="fsInfiniteScroll"' in full and 'data-total="60"' in full and 'data-has-more="1"' in full
    assert "onJump" in full and "buckets:" in full
    # 프래그먼트: 나머지 10건, HTML 문서(doctype) 아님
    frag = client.get("/seller/collect/history?sort=title&fmt=rows&offset=50")
    body = frag.get_data(as_text=True)
    assert body.count("kgp-open-drawer btn btn-success") == 10
    assert "<!doctype" not in body.lower() and "<html" not in body.lower()


def test_component_server_bucket_mode():
    # 레일 v3: 서버 버킷 모드(5000행 미렌더) + lazy 점프(onJump)
    assert "serverMode" in JS and "this.buckets" in JS
    assert "onJump" in JS
    # 서버모드는 DOM 섹션 그룹핑을 하지 않는다(전체 미렌더)
    assert "!this.serverMode && this.list) this.groupSections" in JS
