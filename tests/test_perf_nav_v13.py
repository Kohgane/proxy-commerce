"""tests/test_perf_nav_v13.py — v13 속도 가드: 진행바·프리패치·스켈레톤(체감 속도)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_base_has_progress_and_prefetch():
    html = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert "kgp-progress" in html               # 상단 진행바
    # v52: 링크 rel=prefetch → fetch 메모리 캐시 프리패치로 대체(인스턴트 내비 엔진).
    assert "function prefetch(url)" in html and "fetchDoc" in html  # 내부 링크 프리패치(메모리 캐시)
    assert "prefers-reduced-motion" in html      # reduced-motion 존중(진행바)


def test_app_css_has_skeleton():
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert ".skeleton" in css
    assert "pc-skeleton" in css
    assert "prefers-reduced-motion" in css       # 셔머 정지


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_seller_page_renders_with_perf_script(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert html  # 렌더 정상
    assert "kgp-progress" in html
