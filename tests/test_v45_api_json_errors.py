"""tests/test_v45_api_json_errors.py — P0: API 경로는 절대 HTML 반환 금지(JSON 강제).

증상: 확장 수집 시 '/collect/extension POST 응답이 JSON이 아니라 HTML' → r.json()이
"Unexpected token '<', "<!DOCTYPE"..." 파싱 실패 → 수집 전면 실패. 원인=전역 404/500 핸들러가
HTML(errors/*.html) 반환. 수리: /api/·/webhook/·/cron/ 경로는 404/405/500 모두 JSON.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
OW = Path("src/order_webhook.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_api_404_is_json(client):
    r = client.get("/api/v1/collect/nonexistent-xyz")
    assert r.status_code == 404
    assert "application/json" in r.headers.get("Content-Type", "")
    assert r.get_json() is not None and r.get_json().get("ok") is False


def test_api_405_is_json(client):
    # POST-only 라우트에 GET → 405, JSON
    r = client.get("/api/v1/collect/extension")
    assert r.status_code in (404, 405)
    assert "application/json" in r.headers.get("Content-Type", "")


def test_collect_no_token_is_json_not_html(client):
    # P0 핵심: 미인증이든 오류든 API는 HTML(로그인 페이지·에러 페이지) 대신 **JSON**을 준다.
    #   (상태코드는 전역 인증 상태에 따라 401/502 등일 수 있으나 항상 JSON — r.json() 파싱 성공.)
    r = client.post("/api/v1/collect/extension", json={"url": "https://x.com/g-1"})
    assert "application/json" in r.headers.get("Content-Type", "")
    assert r.get_json() is not None
    assert "<!doctype" not in r.get_data(as_text=True).lower()


def test_html_pages_still_html(client):
    r = client.get("/definitely-not-a-page-xyz")
    assert r.status_code == 404
    body = r.get_data(as_text=True).lower()
    assert "<!doctype" in body or "<html" in body   # 일반 페이지는 HTML 유지


def test_source_contract():
    # API 경로 JSON 강제 헬퍼 + 500 스택 로깅
    assert "_wants_json_error" in OW
    assert '/api/' in OW and '/webhook/' in OW
    assert "logger.exception" in OW
    # 확장: non-JSON(HTML) 응답 → '로그인 확인' 정직 표기
    assert "로그인 확인" in BG and "!doctype" in BG.lower()
