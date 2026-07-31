"""tests/test_v87_oauth_state_diag.py — v87 소셜로그인 state 유실 계측.

오너 확정 사실: 구글이 redirect_uri 검증을 통과해 사인인 화면까지 진행한다(실기기 스크린샷).
콘솔 미등록이면 redirect_uri_mismatch로 그 전에 죽으므로, 남은 주선은 **state 세션 유실**이다.
'보안 오류가 발생했습니다'는 views.py의 state 불일치 분기 한 곳에서만 raise된다.

이 변경은 **로그만 추가**한다 — 동작은 한 글자도 바뀌지 않아야 한다. 그래서 계약의 절반은
'로그가 찍히는가'가 아니라 '**판정이 그대로인가**'다.

배포 후 로그 두 줄 대조로 갈래를 가른다:
  cookie_header_present=false        → 쿠키가 아예 안 돌아옴(브라우저·도메인 갈래)
  쿠키 있고 session_has_state=false  → 세션 저장/백엔드 갈래
  둘 다 true인데 state_equal=false   → 이중 시작(탭 중복·재클릭) 갈래
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

VIEWS = Path("src/auth/views.py").read_text(encoding="utf-8")

START_FIELDS = ("provider", "session_new", "request_host")
CALLBACK_FIELDS = ("provider", "cookie_header_present", "session_has_state",
                   "received_state_present", "state_equal", "request_host", "referrer_host")


def test_start_and_callback_log_lines_exist():
    assert "oauth_start provider=%s" in VIEWS
    assert "oauth_callback provider=%s" in VIEWS
    for f in START_FIELDS:
        assert f in VIEWS, f
    for f in CALLBACK_FIELDS:
        assert f in VIEWS, f


def test_state_value_is_never_logged():
    """시크릿 평문 금지 — 존재·일치 여부만 남긴다. state 자체가 포맷 인자로 들어가면 red."""
    m = re.search(r'logger\.info\(\s*\n?\s*"oauth_callback.*?\)\s*\n', VIEWS, re.S)
    assert m, "콜백 계측 로그를 찾지 못했다"
    seg = m.group(0)
    # 값을 그대로 넘기는 인자가 없어야 한다(bool(...)로 감싼 것만 허용).
    assert "state_param," not in seg, "state 원문이 로그 인자로 들어갔다"
    assert "state_stored," not in seg, "저장된 state 원문이 로그 인자로 들어갔다"
    assert "bool(state_stored)" in seg and "bool(state_param)" in seg


def test_instrumentation_cannot_break_login():
    """계측이 터져도 로그인 흐름을 막지 않는다(로그 때문에 로그인이 죽으면 본말전도)."""
    seg = VIEWS.split("oauth_callback provider=%s")[1].split("if not state_equal:")[0]
    assert "except Exception:" in seg


def test_security_error_still_single_branch():
    """'보안 오류' 문구는 여전히 state 분기 한 곳에서만 나온다(계측이 분기를 늘리지 않았다)."""
    assert VIEWS.count("보안 오류가 발생했습니다") == 1


# ── 동작 불변 ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    return app.test_client()


def _callback(client, **params):
    from urllib.parse import urlencode

    return client.get("/auth/google/callback?" + urlencode(params), follow_redirects=False)


def test_missing_state_still_rejected(client):
    r = _callback(client, code="abc")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_mismatched_state_still_rejected(client):
    with client.session_transaction() as s:
        s["oauth_state_google"] = "STORED-VALUE"
    r = _callback(client, code="abc", state="DIFFERENT-VALUE")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_state_consumed_once(client):
    """state는 pop이라 한 번 쓰면 사라진다 — 재사용 공격 방어가 계측 후에도 그대로."""
    with client.session_transaction() as s:
        s["oauth_state_google"] = "S1"
    _callback(client, code="abc", state="S1")
    with client.session_transaction() as s:
        assert "oauth_state_google" not in s


def test_callback_log_fields_are_emitted(client, caplog):
    """실제 요청에서 필드가 값과 함께 찍히는지 — 소스에만 있고 안 찍히면 진단이 공허하다."""
    with client.session_transaction() as s:
        s["oauth_state_google"] = "S1"
    with caplog.at_level(logging.INFO, logger="src.auth.views"):
        _callback(client, code="abc", state="WRONG")
    line = next((r.getMessage() for r in caplog.records if "oauth_callback" in r.getMessage()), "")
    assert line, "콜백 계측 로그가 안 찍혔다"
    for f in CALLBACK_FIELDS:
        assert f + "=" in line, (f, line)
    assert "state_equal=False" in line
    assert "session_has_state=True" in line
    # 값 유출 0.
    assert "S1" not in line and "WRONG" not in line
