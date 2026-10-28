"""순찰 157 — /health/deep의 resend 체크가 항상 fail이던 것(health_check 부재 → import 오류 삼킴). 이제 정직 3분: 키 없음 skip · 인증 OK · 인증 실패."""
from __future__ import annotations

from unittest import mock

from src.notifications import email_resend as R


def test_no_key_is_skip_not_fail(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False); monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    r = R.health_check()
    assert r["status"] == "skip" and "미설정" in r["detail"]


def test_auth_ok_counts_domains(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_x"); monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    resp = mock.Mock(status_code=200); resp.json.return_value = {"data": [{"id": "a"}, {"id": "b"}]}
    with mock.patch("requests.get", return_value=resp) as g:
        r = R.health_check()
    assert r["status"] == "ok" and "2" in r["detail"]
    assert "re_test_x" not in str(r)                                       # 키 값 노출 0
    assert g.call_args.kwargs["timeout"] == 5


def test_auth_fail_is_fail_with_env_name(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_bad"); monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    with mock.patch("requests.get", return_value=mock.Mock(status_code=401)):
        r = R.health_check()
    assert r["status"] == "fail" and "RESEND_API_KEY" in r["detail"] and "re_bad" not in r["detail"]
