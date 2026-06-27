"""tests/test_v29_tokens.py — v29 PART1: 토큰 본인전용·상시이력·죽은 '발급 완료' 버튼 수정."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")


def test_issue_modal_done_button_is_functional_close():
    # 죽은 '발급 완료' 버튼 수정 — 발급 후 닫기 모드로 전환 + 재활성화(disabled 해제)
    assert "발급 완료 · 닫기" in TPL
    assert "_genBtn.dataset.mode = 'done'" in TPL
    assert "_genBtn.disabled = false;            // 재활성화" in TPL
    assert "_closeGenerateModal" in TPL
    # 저장 확인(모달형 pcConfirm) 후 닫고 목록 갱신(상시 이력)
    assert "pcConfirm(" in TPL and "location.reload()" in TPL
    assert "confirm(" not in TPL.replace("pcConfirm(", "")   # 네이티브 confirm 미사용
    # 다시 열면 상태 초기화
    assert "show.bs.modal" in TPL


def test_copy_button_uses_clipboard_with_fallback():
    assert "navigator.clipboard" in TPL
    assert "writeText" in TPL
    assert "execCommand('copy')" in TPL          # 폴백


def test_secret_once_and_hash_only_messaging():
    assert "지금 한 번만" in TPL                  # 시크릿 1회 표시
    assert "해시로만 저장" in TPL                  # 서버 해시만(원문 재조회 불가)


def test_history_table_shows_masked_value_and_status():
    # 상시 이력: 마스킹 값·스코프·발급일·마지막 사용·만료일·상태(활성/삭제됨)
    for col in ("토큰", "권한", "발급일", "마지막 사용", "만료일", "상태"):
        assert col in TPL, f"이력 컬럼 {col} 누락"
    assert "token_hash_prefix" in TPL            # 마스킹(앞부분만)
    assert "활성" in TPL and "삭제됨" in TPL


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_tokens_page_renders_user_scoped(client):
    # 본인 전용 — list_tokens(user_id)로 현재 사용자 것만(렌더 200)
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/me/tokens")
    assert r.status_code == 200
