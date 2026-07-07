"""tests/test_v45_lang_single_source.py — 한/영 제멋대로 전환 금지(단일 소스·명시 클릭만·기본 ko).

증상(오너): 언어가 스스로 EN으로 바뀜. 근본=/lane/set(수입/수출 선택)이 kgp_lang을 레인 언어로
덮어써 '수출형' 고르면 UI가 EN이 됨. 수리: 레인은 언어를 안 바꾼다. 언어는 명시 토글(/i18n/set)만.
기본 ko. localStorage 미러(쿠키 소실 시 1회 복원, 브라우저 로케일로 자동전환 금지).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

OW = Path("src/order_webhook.py").read_text(encoding="utf-8")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_lane_set_does_not_change_language(client):
    # 레인 '수출형' 선택 → kgp_lang 쿠키를 건드리면 안 된다(자동 EN 전환 원인 제거).
    r = client.get("/lane/set?lane=export", follow_redirects=False)
    lang_cookies = [x for x in r.headers.getlist("Set-Cookie") if x.startswith("kgp_lang=")]
    assert not lang_cookies, f"레인 선택이 언어를 바꿈: {lang_cookies}"
    # 소스에도 lane_set이 kgp_lang을 안 쓴다는 근거
    lane_fn = OW[OW.index("def lane_set"):OW.index("def lane_gate")]
    assert 'set_cookie("kgp_lang"' not in lane_fn


def test_default_is_ko(client):
    import re
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert re.search(r'<html lang="ko"', html)


def test_explicit_toggle_sets_lang(client):
    r = client.get("/i18n/set?lang=en", follow_redirects=False)
    assert any(x.startswith("kgp_lang=en") for x in r.headers.getlist("Set-Cookie"))
    r2 = client.get("/i18n/set?lang=ko", follow_redirects=False)
    assert any(x.startswith("kgp_lang=ko") for x in r2.headers.getlist("Set-Cookie"))


def test_localstorage_mirror_no_autoswitch():
    # localStorage 단일 소스 미러 + 루프방지 복원. 브라우저 로케일 기반 자동 EN 전환 코드 없음.
    assert "localStorage.setItem('kgp_lang'" in BASE
    assert "_kgpLangRestore" in BASE          # 쿠키 소실 시 1회 복원 가드
    # navigator.language로 자동 전환하는 코드가 없어야 한다(자동전환 금지)
    assert "navigator.language" not in BASE


def test_visitor_lang_defaults_ko():
    assert 'else "ko"' in OW or "else 'ko'" in OW
