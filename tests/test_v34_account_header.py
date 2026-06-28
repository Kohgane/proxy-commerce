"""tests/test_v34_account_header.py — v34 P0: 개인화 헤더(내 작업공간·계정·플랜)."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_account_header_shows_for_logged_in_user(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "demo@goga.kr"
        s["user_name"] = "데모 셀러"
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "내 작업공간" in html
    assert "데모 셀러" in html          # 내 계정 표시(공용 아님)
    assert "console-account" in html     # 개인화 패널


def test_account_header_hidden_when_anonymous(client):
    # 비로그인(세션 없음) → 개인화 패널 미노출
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "console-account" not in html


def test_plan_label_injected(client):
    # 플랜 라벨(무료/플러스/프로)이 컨텍스트로 주입돼 표시
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "demo@goga.kr"
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "무료" in html  # 기본 free 플랜 라벨
