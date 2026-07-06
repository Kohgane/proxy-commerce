"""tests/test_v45_collect_diag.py — P0 수집 전면 실패 진단 + 하위호환.

수집 클릭 시 확장/서버가 엔드포인트·HTTP 상태·응답 본문·예외 스택을 로그로 남겨 원인 1줄 규명.
구버전 확장(ext_version 없음) payload는 조용한 실패 대신 400 + '확장 업데이트' 안내.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_server_logs_exception_stack_and_version():
    # 예외는 스택으로(logger.exception), 확장 버전·수신 필드 로깅
    assert "logger.exception" in API and "수집 이력 기록 실패(스택)" in API
    assert "ext_version" in API and "fields=" in API
    # 502·400 응답에 corr-id 포함(로그와 대조)
    assert '"corr": _corr' in API


def test_server_backward_compat_400():
    # 구버전 확장(ext_version 없음) + url 없음 → 조용한 실패 금지, 업데이트 안내
    assert "확장을 최신 버전으로 업데이트" in API
    assert '"update_extension"' in API


def test_extension_logs_endpoint_status_body():
    # background: 엔드포인트·상태·응답 본문 콘솔 로그 + 상태코드를 에러에 포함
    assert "console.log(`[고가수집기] POST" in BG or "console.log(\"[고가수집기]" in BG
    assert "httpStatus" in BG and "response.status" in BG
    assert "await response.text()" in BG          # 500 HTML도 본문 확보(json() 실패 대비)


def test_extension_payload_has_version():
    assert "ext_version" in CS                     # content_script payload
    assert "chrome.runtime.getManifest().version" in CS


def test_fab_toast_shows_http_status():
    assert "HTTP ${resp.httpStatus}" in CS or "httpStatus" in CS


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.auth.personal_tokens as pt
    pt._in_memory[:] = []
    pt._token_cache.clear()
    from src.order_webhook import app
    with app.test_client() as c:
        yield c, pt


def test_url_missing_old_ext_returns_400_update(client):
    c, pt = client
    tok = pt.generate_token(user_id="u1", scopes=["collect.write"])["raw_token"]
    r = c.post("/api/v1/collect/extension",
               headers={"Authorization": f"Bearer {tok}"},
               json={"title": "x"})   # url 없음, ext_version 없음(구버전)
    assert r.status_code == 400
    d = r.get_json()
    assert d["ok"] is False and d.get("update_extension") is True
    assert "업데이트" in d["error"]
