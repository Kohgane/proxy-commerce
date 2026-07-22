"""tests/test_v81_token_hygiene.py — v81 STEP2: 토큰 위생(안정 재사용 + 90일 유휴 만료).

발급 로직을 안정 토큰 재사용으로 — 세션 캐시된 raw 토큰이 활성이면 파일 재다운로드 시 **동일 토큰 재임베드**
(신규 남발 0). 90일 미사용 자동 만료. 토큰 페이지 [최근 사용·용도(권한)] 표시.
계약: 파일 3회 연속 발급 후 토큰 목록 증가 0.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_tokens():
    from src.auth import personal_tokens as pt
    pt._in_memory.clear()
    pt._token_cache.clear()
    yield
    pt._in_memory.clear()
    pt._token_cache.clear()


# ── 단위: 유휴 만료 + token_active ──
def test_idle_expiry_and_token_active():
    from src.auth import personal_tokens as pt
    now = datetime.now(timezone.utc)
    # 갓 발급(사용 없음) → 활성.
    r = pt.generate_token(user_id="u1", scopes=["collect.write"])
    h = r["token_hash"]
    assert pt.token_active("u1", h) is True
    # 다른 사용자 → 미인정.
    assert pt.token_active("other", h) is False
    # 90일+ 미사용 → 유휴 만료(token_active False + validate None).
    row = next(x for x in pt._in_memory if x["token_hash"] == h)
    row["created_at"] = (now - timedelta(days=91)).isoformat()
    row["last_used_at"] = ""
    assert pt._is_idle_expired(row, now) is True
    assert pt.token_active("u1", h) is False
    assert pt.validate_token(r["raw_token"], ["collect.write"]) is None
    # 89일 전 사용 → 아직 활성.
    row["last_used_at"] = (now - timedelta(days=89)).isoformat()
    pt._token_cache.clear()
    assert pt.token_active("u1", h) is True


def test_list_tokens_marks_idle():
    from src.auth import personal_tokens as pt
    r = pt.generate_token(user_id="u1", scopes=["collect.write"])
    row = next(x for x in pt._in_memory if x["token_hash"] == r["token_hash"])
    row["created_at"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    toks = pt.list_tokens("u1")
    assert toks and toks[0]["idle_expired"] is True
    assert "last_used_at" in toks[0] and "scopes" in toks[0]   # 최근 사용·용도(권한)


# ── source-contract: 세션 재사용 헬퍼 ──
def test_bookmarklet_token_helper_source():
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert "def _bookmarklet_token(user_id: str)" in v
    assert 'session.get("bm_token_raw")' in v and 'session["bm_token_raw"] = raw' in v
    assert "_pt.token_active(user_id, ch)" in v
    # 두 라우트가 헬퍼 경유(generate_token 직접 호출 제거).
    assert v.count("raw = _bookmarklet_token(user_id)") >= 2


# ── 세션 재사용 E2E: 파일 3회 연속 발급 → 토큰 목록 증가 0 ──
@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    app.config["SECRET_KEY"] = "test-secret-v81"   # 세션 서명(재사용 캐시 유지)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_email"] = "demo@goga.kr"
        yield c


def test_three_downloads_no_token_growth(client):
    from src.auth import personal_tokens as pt
    # 3회 연속 파일 다운로드(같은 세션).
    for _ in range(3):
        r = client.post("/seller/bookmarklet/file", data={"translate": "1"})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
    toks = pt.list_tokens("u1")
    active = [t for t in toks if not t.get("revoked")]
    assert len(active) == 1, ("파일 3회 발급 후 활성 토큰이 1개여야(신규 남발 0)", len(active), toks)


def test_token_page_shows_idle_badge():
    html = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")
    assert "tok.idle_expired" in html and "유휴 만료" in html
    assert "마지막 사용" in html   # 최근 사용시각
