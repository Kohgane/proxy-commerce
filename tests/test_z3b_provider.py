"""Z3-B(오너 2026-10-05) — mtop 판정 코드(login_required · rgv587 · x5_loop · ok) · 출구 IP 줄 · 코드별 집계.

네트워크 0. 판정 본문은 `tests/fixtures/taobao_mtop/`(출처는 그 폴더 README). 공급자 계약은 test_z3_onebound.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_z3_mtop_auto import FakeSession, _R, _fx

# ── 1) 판정 코드 ─────────────────────────────────────────────────────────────────

def test_987_char_login_jump_body_is_login_required():
    """오너 실측: 핸드셰이크 GET 200 · x5secdata 받음 · 본문 987자에 login_jump → login_required(IP 무관), 거기서 멈춤."""
    from src.collectors import taobao_mtop as T
    body = _fx("x5_handshake_body.txt")
    assert len(body) == 987 and "login_jump" in body and T.login_required(body)
    hs = _R(body, 200, {"x5secdata": "xd7b2268357469676865727d0a1234567890abcdef"})
    s = FakeSession([_R(_fx("x5_referer.txt")), hs])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["kind"] == "login_required" and r["state"] == "blocked" and len(s.calls) == 2      # 재시도 안 함
    assert r["reason"] == "로그인 요구 — 익명 수집 불가(IP 무관). 외부 API 또는 로그인 쿠키 경로 필요."
    assert r["stages"] == {"rgv587": False, "script": True, "x5": True, "login": True, "detail": False}
    assert [ok for _n, ok in T.verdict(r["stages"])] == [True, True, True, False, False]


@pytest.mark.parametrize("marker", ["login_jump", "https://login.m.taobao.com/login.htm?x=1",
                                    "https://login.taobao.com/member/login.jhtml?redirectURL=a"])
def test_login_markers_are_exactly_the_three(marker):
    from src.collectors import taobao_mtop as T
    assert T.login_required(f"<script>location='{marker}'</script>")
    assert not T.login_required("<script>var x = 'loginUrl';</script>")          # 표지 셋 밖은 추측으로 넓히지 않음


def test_rgv587_json_and_body():
    from src.collectors import taobao_mtop as T
    r = T.mtop_ex(FakeSession([_R(_fx("rgv587_punish.json"))]), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["kind"] in ("rgv587", "punish")
    j = T.mtop_ex(FakeSession([_R('{"ret":["RGV587_ERROR::SM::哎哟喂,被挤爆啦"],"data":{}}')]),
                  "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert j["kind"] == "rgv587" and j["stages"]["rgv587"]
    b = T.mtop_ex(FakeSession([_R("<html>RGV587_ERROR 被挤爆啦</html>")]), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert b["kind"] == "rgv587"


def test_json_detail_is_ok():
    from src.collectors import taobao_mtop as T
    s = FakeSession([_R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["kind"] == "ok" and r["stages"]["detail"]


def test_stats_have_per_code_columns(monkeypatch):
    from src.services import mtop_stats as MS
    before = MS.summary(3)["routes"].get("proxy", {})
    MS.record("proxy", "login_required")
    MS.record("proxy", "x5_loop")
    after = MS.summary(3)["routes"]["proxy"]
    assert after["login_required"] - before.get("login_required", 0) == 1
    assert after["x5_loop"] - before.get("x5_loop", 0) == 1
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop").get_data(as_text=True)
    assert 'data-code="login_required"' in h and "로그인 요구" in h and 'data-code="x5_loop"' in h and "x5 루프" in h
    assert "IP 평판" not in h


def test_exit_line_for_every_route(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setattr(T, "exit_ip", lambda sticky="": {"ok": True, "ip": "121.134.5.6", "country": "KR", "bytes": 300})
    assert T.exit_line("proxy", "abcd1234")["how"].startswith("프록시 경유 icanhazip")
    monkeypatch.setenv("MARKET_RELAY_IP", "203.0.113.7")
    rl = T.exit_line("relay2")
    assert rl["ip"] == "203.0.113.7" and "실측 아님" in rl["how"]
    assert "꺼짐" in T.exit_line("direct")["how"]                                  # 테스트는 네트워크 0(conftest)

    class _Resp:
        status_code, text = 200, "198.51.100.4\n"
    import requests
    monkeypatch.setenv("TAOBAO_EXIT_IP_CHECK", "1")
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: _Resp())
    d = T.exit_line("direct")
    assert d["ip"] == "198.51.100.4" and d["how"] == "이 서버 직결 icanhazip 실측"


def test_diag_proxy_login_required_shows_exit_and_conclusion(monkeypatch):
    """완료 조건 1: 프록시 실측에 출구 IP 줄 + login_required 결론 줄."""
    from src.collectors import taobao_mtop as T
    from tests.test_z3_mtop_auto import IPR_STICKY
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    monkeypatch.setattr(T, "exit_ip", lambda sticky="": {"ok": True, "ip": "121.134.5.6", "country": "KR", "bytes": 320})
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700286", "직접 입력"))
    monkeypatch.setattr(T, "session_for", lambda via, sticky="": FakeSession([
        _R(_fx("x5_referer.txt")), _R(_fx("x5_handshake_body.txt"), 200, {"x5secdata": "xd7b22abcdef0123456789"})]))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "733241700286", "via": "proxy"}).get_data(as_text=True)
    assert 'data-role="mtop-exit"' in h and "121.134.5.6" in h and "프록시 경유 icanhazip 실측" in h
    assert 'data-role="mtop-conclusion"' in h and "로그인 요구 — 익명 수집 불가(IP 무관)" in h
    assert "× ④ 로그인 요구 없음" in h


# ── onebound 공급자 계약은 tests/test_z3_onebound.py ─────────────────────────────

def test_z3l_memo_names_no_cookie_guess():
    """Z3-L은 설계 메모만 — 쿠키 이름은 실측 뒤(추측 금지)."""
    memo = (Path(__file__).parent.parent / "docs" / "z3-l.md").read_text(encoding="utf-8")
    assert "실측" in memo and "구현하지 않음" in memo
