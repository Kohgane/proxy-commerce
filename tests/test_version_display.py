"""tests/test_version_display.py — 푸터 버전 자동화 회귀 방지 테스트 (Phase 148).

- 푸터 Phase 번호 == src/version.py CURRENT_PHASE
- 랜딩 페이지 푸터에 "Phase NNN" 형식으로 표시
- 하드코딩된 "Phase 123" (구버전) 문자열이 landing.html에 없어야 함
"""
from __future__ import annotations

import os
import re
import pytest


def test_current_phase_is_integer():
    """CURRENT_PHASE가 양의 정수여야 한다."""
    from src.version import CURRENT_PHASE
    assert isinstance(CURRENT_PHASE, int)
    assert CURRENT_PHASE > 0


def test_current_phase_is_at_least_148():
    """CURRENT_PHASE가 148 이상이어야 한다 (Phase 148 이후 회귀 방지)."""
    from src.version import CURRENT_PHASE
    assert CURRENT_PHASE >= 148, f"CURRENT_PHASE({CURRENT_PHASE})가 148 미만입니다"


def test_get_current_phase_matches_constant():
    """get_current_phase()가 CURRENT_PHASE 상수와 일치해야 한다."""
    from src.version import CURRENT_PHASE, get_current_phase
    assert get_current_phase() == CURRENT_PHASE


def test_get_current_phase_returns_int():
    """get_current_phase()가 int를 반환해야 한다."""
    from src.version import get_current_phase
    phase = get_current_phase()
    assert isinstance(phase, int)
    assert phase > 0


def test_get_version_string_contains_phase():
    """get_version_string()이 'Phase NNN' 형식을 포함해야 한다."""
    from src.version import get_version_string
    vs = get_version_string()
    assert re.search(r"Phase\s+\d+", vs), f"버전 문자열이 'Phase NNN' 형식이 아닙니다: {vs}"


def test_current_phase_override_env(monkeypatch):
    """CURRENT_PHASE_OVERRIDE 환경변수가 설정되면 그 값을 반환해야 한다."""
    monkeypatch.setenv("CURRENT_PHASE_OVERRIDE", "999")
    import importlib
    import src.version as vmod
    importlib.reload(vmod)
    from src.version import get_current_phase
    assert get_current_phase() == 999
    monkeypatch.delenv("CURRENT_PHASE_OVERRIDE")
    importlib.reload(vmod)


def test_landing_html_no_hardcoded_old_phase():
    """landing.html에 'Phase 123' 하드코딩 문자열이 없어야 한다 (회귀 방지)."""
    landing_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "templates", "landing.html"
    )
    with open(landing_path, encoding="utf-8") as f:
        content = f.read()
    # Phase 123 하드코딩 금지
    assert "Phase 123" not in content, (
        "landing.html에 'Phase 123' 하드코딩 문자열이 남아 있습니다. "
        "{{ current_phase }} 동적 렌더를 사용하세요."
    )


def test_landing_html_uses_dynamic_phase():
    """landing.html 푸터가 {{ current_phase }} 동적 템플릿 변수를 사용해야 한다."""
    landing_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "templates", "landing.html"
    )
    with open(landing_path, encoding="utf-8") as f:
        content = f.read()
    assert "current_phase" in content, (
        "landing.html 푸터에 {{ current_phase }} 변수가 없습니다."
    )


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    os.environ.setdefault("ROOT_REDIRECT", "landing")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


def test_landing_page_footer_shows_current_phase(client):
    """랜딩 페이지 푸터에 현재 Phase가 표시되어야 한다."""
    from src.version import CURRENT_PHASE
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert f"Phase {CURRENT_PHASE}" in html, (
        f"랜딩 페이지 푸터에 'Phase {CURRENT_PHASE}'이 표시되지 않습니다. 실제 내용 (일부): {html[:500]}"
    )
