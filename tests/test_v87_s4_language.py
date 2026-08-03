"""tests/test_v87_s4_language.py — v87-S4: 언어 정책 계약(명시 선택만 유효 · 한국어 폴백).

■ 오너 지정 계약
1. **명시 선택만 유효.** 헤더 토글(/i18n/set)로 고른 값이 쿠키에 저장되고 전 페이지에 일관 적용된다.
2. **Accept-Language 자동 전환 금지.** 브라우저가 영어라고 UI가 제멋대로 영어가 되지 않는다.
3. **미번역은 한국어 폴백.** en 문구가 없으면 ko로 떨어진다 — 키나 빈칸이 화면에 남지 않는다.

■ 기계 판정 범위(정직)
템플릿이 쓰는 `t('키')`가 전부 STRINGS에 있고 ko/en 쌍을 갖췄는지는 **여기서 전수 검사**된다.
반면 `/dashboard/*`(web_ui.py)는 i18n을 아예 쓰지 않는 하드코딩 한국어라 EN 모드에서도 한국어로 남는다
— 그건 문자열 누락이 아니라 **콘솔 이원화 구조 문제**라서 이 파일이 판정하지 않는다(오너 보고서 항목).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.seller_console.i18n import DEFAULT_LANG, STRINGS, normalize_lang, t

_TEMPLATE_DIRS = ("src/seller_console/templates", "src/templates")
_KEY_RE = re.compile(r"""t\(\s*['"]([a-z0-9_]+(?:\.[a-z0-9_]+)+)['"]""")


def _template_keys() -> set[str]:
    keys = set()
    for d in _TEMPLATE_DIRS:
        for p in Path(d).rglob("*.html"):
            keys |= set(_KEY_RE.findall(p.read_text(encoding="utf-8")))
    return keys


# ── 1. 명시 선택만 유효 ────────────────────────────────────────────────────────

def test_explicit_toggle_sets_the_cookie(client_app):
    r = client_app.get("/i18n/set?lang=en&next=/", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "kgp_lang=en" in "; ".join(r.headers.getlist("Set-Cookie"))


def test_unknown_lang_falls_back_to_korean(client_app):
    r = client_app.get("/i18n/set?lang=zz&next=/", follow_redirects=False)
    assert "kgp_lang=ko" in "; ".join(r.headers.getlist("Set-Cookie"))


# ── 2. Accept-Language 자동 전환 금지 ─────────────────────────────────────────

def test_accept_language_does_not_switch_ui_language():
    """★ 이 계약이 '무단 전환'의 방지선 — 쿠키가 없으면 무조건 한국어다."""
    from src import order_webhook as ow
    with ow.app.test_request_context("/", headers={"Accept-Language": "en-US,en;q=0.9"}):
        assert ow._visitor_lang() == "ko"


def test_lane_choice_does_not_touch_language():
    """수입/수출 레인을 골라도 언어는 안 바뀐다(과거 '수출형→UI 영어' 회귀 방지)."""
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    seg = src.split("def lane_set")[1].split("\n@app.")[0]
    assert 'set_cookie("kgp_lang"' not in seg, "레인 선택이 언어 쿠키를 덮어쓴다"


@pytest.mark.parametrize("hdr", ["en-US,en;q=0.9", "ja-JP", "zh-CN", ""])
def test_language_is_korean_for_every_browser_locale(client_app, hdr):
    from src import order_webhook as ow
    with ow.app.test_request_context("/", headers={"Accept-Language": hdr}):
        assert ow._visitor_lang() == "ko"


# ── 3. 한국어 폴백 · 혼재 방지 ────────────────────────────────────────────────

def test_missing_english_falls_back_to_korean(monkeypatch):
    monkeypatch.setitem(STRINGS, "zz.only_ko", {"ko": "한국어만"})
    assert t("zz.only_ko", "en") == "한국어만"


def test_normalize_lang_defaults_to_korean():
    for bad in (None, "", "fr", "ja", "  "):
        assert normalize_lang(bad) == DEFAULT_LANG == "ko"


def test_every_template_key_exists():
    """키가 없으면 화면에 `nav.foo` 같은 **개발 표기**가 그대로 노출된다."""
    missing = sorted(k for k in _template_keys() if k not in STRINGS)
    assert not missing, f"STRINGS에 없는 키가 템플릿에서 쓰인다: {missing}"


def test_every_template_key_has_both_languages():
    """한쪽만 있으면 그 화면만 언어가 튄다(혼재 화면 = red)."""
    bad = sorted(k for k in _template_keys()
                 if not (STRINGS.get(k, {}).get("ko") and STRINGS.get(k, {}).get("en")))
    assert not bad, f"ko/en 쌍이 안 갖춰진 키: {bad}"


def test_no_raw_key_leaks_into_rendered_console(client_app):
    """실제로 렌더된 화면에 점(.)으로 이어진 키 문자열이 남아 있지 않은지."""
    body = client_app.get("/seller/", follow_redirects=True).get_data(as_text=True)
    leaked = set(re.findall(r">\s*((?:nav|action|fb|lang|collect|orders|markets)\.[a-z0-9_.]+)\s*<", body))
    assert not leaked, f"번역 키가 그대로 화면에 노출됨: {sorted(leaked)}"


@pytest.fixture()
def client_app():
    import os
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    return app.test_client()
