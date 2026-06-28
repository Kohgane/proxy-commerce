"""tests/test_v35_sourcing_grid.py — v35 P0: 소싱 카드 그리드 복원 + 이미지 깨짐 수정."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SOURCING = Path("src/seller_console/templates/sourcing.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_grid_restored_multicolumn():
    # 세로 일렬 금지 → CSS Grid auto-fill 다열(뷰포트 무관). 부트스트랩 col 의존 제거.
    assert "repeat(auto-fill,minmax(280px,1fr))" in SOURCING
    assert "col-12 col-sm-6 col-lg-4" not in SOURCING


def test_image_hotlink_and_placeholder():
    # 네이버 핫링크 차단 우회 + 실패 시 박스 유지·아이콘 플레이스홀더(빈 색 박스 금지)
    assert 'referrerpolicy="no-referrer"' in SOURCING
    assert 'bi bi-image' in SOURCING                       # 플레이스홀더 아이콘
    # 실패 시 박스(부모) 통째로 숨기지 않음 → 이미지 자체만 숨김
    assert "this.parentElement.style.display='none'" not in SOURCING


def test_card_overflow_guard():
    # 버튼/콘텐츠가 카드 폭을 넘지 않도록 카드 overflow 처리
    assert "overflow:hidden;" in SOURCING


def test_sourcing_page_renders(client):
    resp = client.get("/seller/sourcing?keyword=에코백")
    assert resp.status_code == 200
