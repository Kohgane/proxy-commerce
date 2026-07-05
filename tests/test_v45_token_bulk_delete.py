"""tests/test_v45_token_bulk_delete.py — 토큰 삭제영속·다중선택 삭제·확장 401만 재발급(요청 3).

①삭제→재조회 부활 0(PG durable) ②체크박스 다중선택 삭제 라우트 ③확장 401/미인증일 때만 재발급 안내.
PG 경로 실검증은 DATABASE_URL 시만, 계약/UI는 상시.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        yield c


def test_multiselect_ui_present():
    # ② 체크박스 다중선택 + 선택 삭제 버튼 + 전체선택
    assert 'id="tokSelectAll"' in TPL
    assert "tok-check" in TPL
    assert 'id="bulkRevokeBtn"' in TPL
    assert "/seller/me/tokens/revoke-bulk" in TPL


def test_bulk_route_source_contract():
    assert '@bp.post("/me/tokens/revoke-bulk")' in VIEWS
    assert "token_hashes" in VIEWS
    assert "revoke_token" in VIEWS
    assert '"revoked_count"' in VIEWS


def test_extension_reauth_only_on_401():
    # ③ 재발급 안내는 authRequired(401·미설정)일 때만 — 매 페이지 토스트 금지(클릭 시에만)
    assert "resp.authRequired" in CS
    assert "다시 설정" in CS
    # background: 401일 때만 authRequired, 미인증 자동 알림 남발 0
    assert "response.status === 401" in BG
    assert "미인증 자동 토스트 남발 금지" in BG


def test_bulk_route_bad_request(client):
    r = client.post("/seller/me/tokens/revoke-bulk", json={"token_hashes": []})
    assert r.status_code == 400
    assert r.get_json().get("ok") is False


@pytest.mark.skipif(not (os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")),
                    reason="DATABASE_URL 미설정 — PG durable 검증 skip")
def test_bulk_delete_durable_pg(client, monkeypatch):
    import src.db.pg as pg
    from src.auth import personal_tokens as pt
    pg.reset_state(); pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE user_tokens")
    monkeypatch.setattr("src.seller_console.views._current_user_id", lambda: "u1")
    monkeypatch.setattr("src.seller_console.views._seller_identities", lambda: {"u1"})
    hashes = [pt.generate_token(user_id="u1", scopes=["collect.write"])["token_hash"] for _ in range(3)]
    # 3개 중 2개 다중 삭제
    r = client.post("/seller/me/tokens/revoke-bulk", json={"token_hashes": hashes[:2]})
    assert r.get_json()["revoked_count"] == 2
    # 재조회(재시작) 부활 0 — 남은 활성 1개
    pg.reset_state()
    active = [t for t in pt.list_tokens(user_id="u1") if not t.get("revoked")]
    assert len(active) == 1
    pg.reset_state()
