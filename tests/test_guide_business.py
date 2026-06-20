"""tests/test_guide_business.py — 사업자등록 가이드 (Phase 243, 브리프 §4.3)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_business_guide_page_200(client):
    resp = client.get("/seller/guide/business")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # 3단계 + 공식 딥링크 + 면책
    assert "사업자 등록" in html
    assert "통신판매업 신고" in html
    assert "구매대행" in html
    assert "hometax.go.kr" in html
    assert "gov.kr" in html
    assert "면책" in html  # 디스클레이머


def test_business_guide_has_checklist(client):
    html = client.get("/seller/guide/business").get_data(as_text=True)
    assert "체크리스트" in html
    assert "biz-check" in html


def test_nav_links_to_business_guide(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/guide/business" in html
