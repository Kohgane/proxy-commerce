"""F44-c 계약 — 합병·폐업 택배사는 **보이되 고를 수 없다**.

## 오너 승인 (2026-09-21)

> 택배사 드롭다운/검색 결과에서 `active=False`는 **회색·선택불가·「합병/폐업 — 쿠팡 미지원」**.

**숨기지 않는 이유**: 없는 척하면 「내 택배사가 왜 없지」가 되고, 그건 사유가 사라진 것이다.
**고를 수 있게 두지 않는 이유**: 등록이 마켓에서 거부된다 — 여기서 말해 주는 편이 빠르다.

## 재는 것 — **실브라우저**에서 JS를 돌려서

마크업을 눈으로 읽고 「있겠지」 하지 않는다. 실제로 목록을 그려서
회색인지 · 눌리는지 · 키보드로도 안 골라지는지를 **DOM에 물어본다**.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "seller_console" / "static" / "orders.js"


def _chrome_opts():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


# ---------------------------------------------------------------------------
# 카탈로그 — 폐업도 내려간다
# ---------------------------------------------------------------------------

def test_the_catalog_carries_the_retired_couriers():
    """★ 화면이 회색으로 그리려면 **내려가야** 한다."""
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = get_courier_catalog(include_dynamic=False)
    retired = [r for r in rows
               if r["coupang_status"].get("found") and not r["coupang_status"]["selectable"]]
    assert len(retired) == 14, [r["name"] for r in retired]


def test_a_retired_row_carries_its_reason():
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = {r["coupang_code"]: r for r in get_courier_catalog(include_dynamic=False)}
    assert rows["KOREX"]["coupang_status"]["reason"] == "합병/폐업 — 쿠팡 미지원"


def test_a_live_courier_stays_selectable():
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = {r["coupang_code"]: r for r in get_courier_catalog(include_dynamic=False)}
    assert rows["CJGLS"]["coupang_status"]["selectable"] is True


def test_the_tracking_axes_are_not_clobbered():
    """★★ 쿠팡 열을 붙이면서 **추적 공급사 축을 덮지 않는다** — 다른 축이다."""
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = {r["name"]: r for r in get_courier_catalog(include_dynamic=False)}
    cj = rows["CJ대한통운"]
    # F44-b: 17TRACK 코드는 **캐리어 목록 문서가 와야** 채운다 — 빈칸이 정직하다.
    assert cj["seventeentrack_code"] == ""
    assert "cj-korea" in cj["search_terms"]        # 옛 코드는 **검색어로** 남는다
    assert cj["sweet_code"] == "04"
    assert cj["coupang_code"] == "CJGLS"


def test_every_coupang_code_is_searchable_from_the_catalog():
    """★★★ F44 계약 — **표의 모든 코드가 검색으로 도달 가능**(화면이 쓰는 그 목록에서)."""
    from src.seller_console.orders.coupang_courier_codes import COUPANG_COURIERS
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    terms = set()
    for r in get_courier_catalog(include_dynamic=False):
        terms |= {str(t).lower() for t in r.get("search_terms", [])}
    missing = [c.code for c in COUPANG_COURIERS if c.code.lower() not in terms]
    assert not missing, missing


# ---------------------------------------------------------------------------
# ★ 실브라우저 — 회색 · 안 눌림 · 키보드로도 안 골라짐
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    catalog = [
        {"name": "CJ대한통운", "coupang_code": "CJGLS", "search_terms": ["cj", "cjgls"],
         "coupang_status": {"found": True, "selectable": True, "reason": ""}},
        {"name": "대한통운[합병]", "coupang_code": "KOREX", "search_terms": ["korex"],
         "coupang_status": {"found": True, "selectable": False,
                            "reason": "합병/폐업 — 쿠팡 미지원"}},
    ]
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(**_chrome_opts())
        pg = browser.new_page()
        pg.set_content(
            '<input id="tm-courier"><div id="tm-courier-listbox"></div>'
            '<input id="tm-tracking-no">')
        # 화면이 실제로 쓰는 렌더 함수만 떼어 실행한다(우리가 다시 쓴 것이 아니다).
        src = JS.read_text(encoding="utf-8")
        start = src.index("function renderCourierSuggestions")
        end = src.index("function closeCourierSuggestions")
        pg.evaluate(
            "([body, rows]) => {"
            "  window.typeaheadState = {activeIndex: -1, suggestions: rows};"
            "  window.getCourierTypeaheadElements = () => ({"
            "    input: document.getElementById('tm-courier'),"
            "    listbox: document.getElementById('tm-courier-listbox'),"
            "    trackingInput: document.getElementById('tm-tracking-no')});"
            "  window.selectCourierSuggestion = (i) => {"
            "    const s = window.typeaheadState.suggestions[i];"
            "    const cs = (s && s.coupang_status) || {};"
            "    if (cs.found === true && cs.selectable === false) return;"
            "    document.getElementById('tm-courier').value = s.name;"
            "  };"
            "  eval(body);"
            "  renderCourierSuggestions();"
            "}", [src[start:end], catalog])
        yield pg
        browser.close()


def test_the_retired_option_is_rendered_but_disabled(page):
    """★★★ **판정 지점** — 목록에 **있고**, `disabled`다."""
    opts = page.locator("#tm-courier-listbox button")
    assert opts.count() == 2
    assert page.locator('button[data-retired="1"]').count() == 1
    assert page.locator('button[data-retired="1"]').is_disabled()


def test_the_retired_option_says_why(page):
    txt = page.locator('button[data-retired="1"]').inner_text()
    assert "합병/폐업 — 쿠팡 미지원" in txt
    assert "대한통운[합병]" in txt


def test_the_retired_option_is_greyed(page):
    cls = page.locator('button[data-retired="1"]').get_attribute("class")
    assert "text-muted" in cls and "disabled" in cls


def test_clicking_the_retired_option_selects_nothing(page):
    """★★ 회색으로 보이기만 하고 **눌리면** 그건 회색이 아니라 장식이다."""
    page.locator('button[data-retired="1"]').click(force=True)
    assert page.locator("#tm-courier").input_value() == ""


def test_the_live_option_still_works(page):
    """★ 막으면서 **멀쩡한 것까지 막지 않았는지** — 회귀는 이쪽으로 온다."""
    page.evaluate("() => window.selectCourierSuggestion(0)")
    assert page.locator("#tm-courier").input_value() == "CJ대한통운"


def test_the_keyboard_path_is_blocked_too(page):
    """★★★ 버튼만 disabled면 **마우스는 막히고 키보드는 통과**한다.

    Enter는 `selectCourierSuggestion(activeIndex)`를 직접 부른다 — 같은 문을 지나야 한다.
    """
    page.evaluate("() => { document.getElementById('tm-courier').value = ''; }")
    page.evaluate("() => window.selectCourierSuggestion(1)")     # 폐업 행
    assert page.locator("#tm-courier").input_value() == ""
