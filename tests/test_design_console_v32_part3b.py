"""tests/test_design_console_v32_part3b.py — v32 PART3 #2: orders/markets 콘솔 디자인 격상."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_orders_kpi_editorial_upgrade(client):
    html = client.get("/seller/orders").get_data(as_text=True)
    # 대시보드와 동일 패턴: 세리프 대형 KPI + 오버라인 라벨 + 토큰 악센트 카드 + 금 헤어라인.
    # 6-e에서 컴포넌트가 console-kpi-* → od-stat-*로 옮겼다 — **뜻은 그대로, 이름만 재조준.**
    assert "od-stat-v" in html                      # 세리프 대형 숫자
    assert "od-stat-k" in html                      # 오버라인 라벨
    assert "console-kpi-label" in html              # 페이지 오버라인은 공통 컴포넌트 유지
    assert "od-stat" in html                        # 토큰 악센트 타일
    assert "pc-hairline" in html
    # 옛 마크업/글리프 잔재 0
    assert "fs-2 fw-bold text-primary" not in html
    assert "⟳" not in html               # 단일 아이콘셋(bi-*)으로 교체


def test_markets_header_overline(client):
    html = client.get("/seller/markets").get_data(as_text=True)
    assert "console-kpi-label" in html   # 오버라인 라벨(에디토리얼 키커)


def test_collect_history_summary_editorial(client):
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    store.append(source="extension", url="https://x.com/p", title="t", seller_id="u1")
    try:
        with client.session_transaction() as s:
            s["user_id"] = "u1"
        html = client.get("/seller/collect/history").get_data(as_text=True)
        # ★ Stage 6-c(2026-09-03): 요약 4장이 **카드 1장 + 기하 타일 4**로 바뀌었다(6-a 문법 승계).
        #   핀의 뜻("세리프 대형 KPI + 오버라인 라벨")은 그대로다 — 클래스만 op-* 세대로 옮긴다.
        #   `op-tile-v`가 `var(--font-display)`를 쓰는 건 app.css 6-a 슬라이스가 보증한다.
        assert "op-tile-v" in html                # 세리프 대형 KPI
        assert "op-tile-k" in html                # 오버라인 라벨
        assert "console-kpi-label" in html        # 헤더 오버라인은 유지
        assert "fs-4 fw-bold" not in html         # 옛 마크업 제거
    finally:
        store._in_memory[:] = []


def test_sourcing_hub_editorial(client):
    html = client.get("/seller/sourcing?keyword=에코백").get_data(as_text=True)
    assert "console-kpi-label" in html       # 헤더/분석 오버라인
    assert "var(--font-display)" in html      # 분석 수치 세리프
    assert "AI 소싱·등록" in html              # 기존 식별 문구 보존(무회귀)
