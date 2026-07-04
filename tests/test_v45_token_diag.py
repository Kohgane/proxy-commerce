"""tests/test_v45_token_diag.py — 북마클릿 토큰 발급 실패 진단 + 회복.

버그: '토큰을 저장하지 못했어요' 반복(append는 성공했는데 자기검증 읽기가 429로 실패 → 가짜 실패).
수리: ①실패 원인 1줄 분류·로깅 ②429/5xx 재시도 ③읽기 실패는 관대 처리(append 성공이면 durable).
근본 해결은 user_tokens Supabase 이관(트랜잭션 커밋 = durable).
"""
from __future__ import annotations

import pytest

from src.auth import personal_tokens as pt


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _APIErr(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg or f"APIError {code}")
        self.response = _Resp(code)


def test_classify_causes():
    assert "429" in pt._classify_token_error(_APIErr(429))
    assert "권한" in pt._classify_token_error(_APIErr(403))
    assert "권한" in pt._classify_token_error(_APIErr(401))
    assert "타임아웃" in pt._classify_token_error(_APIErr(503))
    assert "잠금" in pt._classify_token_error(Exception("row is locked"))
    assert "기타" in pt._classify_token_error(ValueError("weird"))


class _FakeWS:
    def append_row(self, row):
        return None

    def row_values(self, n):
        return list(pt._HEADERS) if hasattr(pt, "_HEADERS") else ["token_hash"]


@pytest.fixture
def sheet_mode(monkeypatch):
    # PG 미사용(폴백) + Sheets 설정된 것처럼
    monkeypatch.setattr(pt, "_pg_tokens", lambda: None)
    monkeypatch.setattr(pt, "_SHEET_ID", "sheet-x", raising=False)
    monkeypatch.setattr(pt, "_get_worksheet", lambda: _FakeWS())
    monkeypatch.setattr(pt, "_ensure_headers", lambda ws: None)
    monkeypatch.setattr(pt.time, "sleep", lambda *_a, **_k: None)
    yield


def test_lenient_readback_append_ok_read_429_is_success(sheet_mode, monkeypatch):
    """append 성공 + 자기검증 읽기 429 → 가짜 실패 아님(durable 발급)."""
    monkeypatch.setattr(pt, "_find_token_row", lambda token_hash, ws=None: (_ for _ in ()).throw(_APIErr(429)))
    r = pt.generate_token("u1", scopes=["collect.write"])
    assert r["durable"] is True and r["raw_token"].startswith("kgp_")


def test_append_429_retried_then_ok(sheet_mode, monkeypatch):
    calls = {"n": 0}
    ws = _FakeWS()
    def flaky_append(row):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _APIErr(429)
        return None
    ws.append_row = flaky_append
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)
    # 검증 읽기는 매칭 성공 반환
    monkeypatch.setattr(pt, "_find_token_row", lambda token_hash, ws=None: {"token_hash": token_hash})
    monkeypatch.setattr(pt, "_token_row_matches_saved", lambda *a, **k: True)
    r = pt.generate_token("u1")
    assert r["durable"] is True and calls["n"] == 2   # 1회 429 후 재시도 성공


def test_genuine_failure_reports_cause(sheet_mode, monkeypatch):
    """append가 계속 403(권한) → TokenStoreCommitError, 메시지에 원인 포함."""
    def perm(row):
        raise _APIErr(403)
    ws = _FakeWS(); ws.append_row = perm
    monkeypatch.setattr(pt, "_get_worksheet", lambda: ws)
    with pytest.raises(pt.TokenStoreCommitError) as ei:
        pt.generate_token("u1")
    assert "권한" in str(ei.value)                     # 원인 1줄 안내


def test_route_returns_cause_message():
    """라우트가 TokenStoreCommitError 메시지(원인 포함)를 그대로 전달(503)."""
    from pathlib import Path
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert '"error": str(exc)' in v and "TokenStoreCommitError" in v
