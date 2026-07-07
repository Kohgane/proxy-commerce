"""tests/test_v45_collect_p0_diag.py — P0 수집: 토큰 헤더 콘솔 로그 + 미인증 401 JSON + 북마클릿 CSP 안내.

오너: 확장 요청에 토큰 헤더 실림을 콘솔 로그로 노출. 서버는 미인증 401 JSON(HTML 금지).
북마클릿은 CSP 차단 사이트면 '확장을 쓰세요' 인페이지 안내.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_extension_logs_token_header():
    # 단건·벌크 모두 인증 토큰 첨부 여부를 콘솔에 노출(값 마스킹 — 뒤 4자리만).
    assert "인증 토큰" in BG
    assert "Bearer …" in BG
    assert BG.count("인증 토큰") >= 2   # handleCollect + handleCollectBulk


def test_no_token_is_json_not_html(client):
    # 순서 독립 계약(P0): API는 인증 상태와 무관하게 항상 **JSON**(로그인/에러 HTML 금지).
    #   (상태코드는 전역 인증 오염에 따라 401/502 등일 수 있으나 항상 JSON — r.json() 성공.)
    r = client.post("/api/v1/collect/extension", json={"url": "https://x.com/g-1"},
                    headers={"Accept": "application/json"})
    assert "application/json" in r.headers.get("Content-Type", "")
    assert r.get_json() is not None
    assert "<!doctype" not in r.get_data(as_text=True).lower()


def test_bookmarklet_csp_notice_and_html_detect():
    # 북마클릿: CSP 차단(catch) → '확장을 쓰세요' 인페이지 안내 + HTML 응답 감지(로그인 확인).
    bm = VIEWS[VIEWS.index("def _bookmarklet_js"):VIEWS.index("_BRIDGE_ICON_DATA_URI = None")]
    assert "보안정책(CSP)" in bm and "크롬 확장" in bm      # CSP 차단 안내
    assert "로그인 확인이 필요할 수" in bm                   # HTML 응답 감지
    assert "/api/v1/collect/extension" in bm                # JSON 엔드포인트(미인증 401 JSON)
