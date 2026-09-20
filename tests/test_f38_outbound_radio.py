"""F38 계약 — 「고른 값으로 칸 채우기」가 출고지를 건너뛰지 않는다.

## 실측 (오너 2026-09-20)

「불러오기」에 **출고지 2개**(22796911 / 25099966)가 왔는데
**「고른 값으로 칸 채우기」가 OUTBOUND를 건너뛰었다.**

## 코드로 확정한 것 — 라디오는 그려졌다

`renderLookup`은 `return_centers`·`outbound_places` **둘 다** 돌며 라디오를 그린다.
빈 것은 **`entry.values`**였다 — 응답의 키 이름이 `OUTBOUND_FIELD_CANDIDATES`에 없어
`_map_row`가 아무것도 못 골랐다. 그래서 채우기가 **조용히 건너뛰었고**,
토스트는 「N개 칸을 채웠어요」라고만 했다(빈 칸은 말하지 않았다).

> ★★ **못 채운 것을 말하지 않으면, 사람은 채워진 줄 안다.**

## 이 판이 하는 것 / 안 하는 것

**안 한다** — 키 이름을 지어내지 않는다. 오너가 준 것은 **값**(22796911)이지 키가 아니다.
`OUTBOUND_FIELD_CANDIDATES`는 그대로 둔다(F29-4·F34-3의 규율).

**한다** — ①못 고른 칸마다 **응답이 실제로 준 키** 목록에서 고르는 자리를 낸다
(사람이 한 번 고르면 그 값이 칸에 들어간다) ②채우기가 **못 고른 블록을 말한다**.

키 이름 실측이 오면 후보 사전에 넣어 자동화한다 — 그때까지 사람이 막히지 않는다.

라이브 호출 0 · **실제 브라우저에서 JS를 돌린다**(정적 HTML 파싱은 JS 결함을 못 본다 — F28 규율).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src/seller_console/templates/markets_connect.html"

# 오너 실측 응답 모양: 출고지 2개, 우리가 고른 값은 **없다**(키 이름 미실측).
DATA = {
    "return_centers": {"ok": True, "entries": [
        {"label": "장말로", "values": {"COUPANG_RETURN_CENTER_CODE": "1002166041"},
         "raw": {"returnCenterCode": "1002166041", "shippingPlaceName": "장말로"}},
    ]},
    "outbound_places": {"ok": True, "entries": [
        {"label": "", "values": {},
         "raw": {"알수없는키": "22796911", "placeName": "1출고지"}},
        {"label": "", "values": {},
         "raw": {"알수없는키": "25099966", "placeName": "2출고지"}},
    ]},
    "unmapped": ["COUPANG_OUTBOUND_SHIPPING_PLACE_CODE"],
}


def _render_lookup_source() -> str:
    src = TPL.read_text(encoding="utf-8")
    m = re.search(r"function renderLookup\(form, data\) \{.*?\n\}\n", src, re.S)
    assert m, "renderLookup을 못 찾았다 — 계약이 헛것을 잰다"
    return m.group(0)


def _chrome_opts():
    """레포에 이미 있는 실행 경로 규약을 그대로 쓴다(`test_f28…`와 동형 — 두 벌 금지)."""
    import glob
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(**_chrome_opts())
        pg = browser.new_page()
        pg.set_content(
            "<form class='f'>"
            "<input name='COUPANG_RETURN_CENTER_CODE'>"
            "<input name='COUPANG_OUTBOUND_SHIPPING_PLACE_CODE'>"
            "<div id='out'></div></form>")
        pg.add_script_tag(content=(
            "window.__toasts=[];"
            "function kgpEscapeForHtml(s){const d=document.createElement('div');"
            "d.textContent=String(s==null?'':s);return d.innerHTML;}"
            "function pcToast(m,k){window.__toasts.push([m,k]);}\n"
            + _render_lookup_source()))
        yield pg
        browser.close()


def _render(page):
    page.evaluate(
        "d => { window.__toasts=[]; const f=document.querySelector('.f');"
        " f.querySelectorAll('input[name]').forEach(i=>i.value='');"
        " document.getElementById('out').innerHTML = renderLookup(f, d); }", DATA)
    page.wait_for_timeout(30)     # apply 핸들러는 setTimeout(…, 0)에서 붙는다


# ---------------------------------------------------------------------------
# ① 라디오는 원래 그려졌다 — 그 사실을 고정한다
# ---------------------------------------------------------------------------

def test_two_outbound_places_draw_two_radios(page):
    """★ 오너가 「라디오가 안 그려졌다」고 본 것 — 실제로는 그려진다. 문제는 그다음이었다."""
    _render(page)
    n = page.evaluate("document.querySelectorAll('input[name=\"lk-outbound_places\"]').length")
    assert n == 2


def test_a_single_entry_is_preselected(page):
    """1개면 자동 선택(오너: 「1개면 자동」)."""
    _render(page)
    checked = page.evaluate(
        "document.querySelector('input[name=\"lk-return_centers\"]').checked")
    assert checked is True


# ---------------------------------------------------------------------------
# ② 못 고른 칸은 사람이 고를 수 있다 — 키 이름은 지어내지 않는다
# ---------------------------------------------------------------------------

def test_an_unmapped_field_gets_a_picker_of_real_response_keys(page):
    """★★ **F38의 판정 지점** — 응답이 **실제로 준 키**만 보기로 낸다."""
    _render(page)
    opts = page.evaluate(
        "Array.from(document.querySelectorAll('select[data-lk-manual=\"COUPANG_OUTBOUND_SHIPPING_PLACE_CODE\"] option'))"
        ".map(o=>o.textContent)")
    assert any("알수없는키 = 22796911" in o for o in opts), opts
    assert any("알수없는키 = 25099966" in o for o in opts), opts


def test_picking_a_key_fills_the_field(page):
    """★★ 고르면 **그 칸에 들어간다** — 오너가 손으로 넣던 값을 화면이 채운다."""
    _render(page)
    page.evaluate(
        "() => { const s=document.querySelector('select[data-lk-manual]');"
        " s.value = Array.from(s.options).find(o=>o.textContent.includes('22796911')).value;"
        " document.querySelector('[data-action=\"lookup-apply\"]').click(); }")
    val = page.evaluate(
        "document.querySelector('[name=\"COUPANG_OUTBOUND_SHIPPING_PLACE_CODE\"]').value")
    assert val == "22796911"


def test_the_mapped_field_still_fills_automatically(page):
    """무회귀 — 우리가 고를 수 있는 칸은 그대로 자동으로 찬다."""
    _render(page)
    page.evaluate("document.querySelector('[data-action=\"lookup-apply\"]').click()")
    val = page.evaluate("document.querySelector('[name=\"COUPANG_RETURN_CENTER_CODE\"]').value")
    assert val == "1002166041"


def test_it_says_which_block_it_could_not_map(page):
    """★★ **조용히 건너뛰지 않는다** — 「N개 채웠어요」만 보고 빈 칸을 모르던 그 자리.

    오너가 한 동작 그대로: **출고지 라디오를 고르고** 채우기를 누른다.
    (2개면 미리 선택되지 않으므로, 고르지 않으면 그 블록을 아예 지나지 않는다.)
    """
    _render(page)
    page.evaluate(
        "() => { document.querySelector('input[name=\"lk-outbound_places\"]').checked = true;"
        " document.querySelector('[data-action=\"lookup-apply\"]').click(); }")
    msg = page.evaluate("window.__toasts.map(t=>t[0]).join(' ')")
    assert "출고지" in msg and "고르지 못했어요" in msg, msg


def test_nothing_picked_leaves_the_field_empty(page):
    """★ 고르지 않으면 **비워 둔다** — 아무 값이나 넣지 않는다."""
    _render(page)
    page.evaluate("document.querySelector('[data-action=\"lookup-apply\"]').click()")
    val = page.evaluate(
        "document.querySelector('[name=\"COUPANG_OUTBOUND_SHIPPING_PLACE_CODE\"]').value")
    assert val == ""


# ---------------------------------------------------------------------------
# ③ 후보 사전은 그대로다 (F29-4·F34-3 규율)
# ---------------------------------------------------------------------------

def test_the_candidate_dictionary_was_not_invented():
    """★ 오너가 준 것은 **값**(22796911)이지 키가 아니다 — 후보를 늘리지 않았다."""
    from src.seller_console.coupang_shipping_lookup import OUTBOUND_FIELD_CANDIDATES
    assert OUTBOUND_FIELD_CANDIDATES["COUPANG_OUTBOUND_SHIPPING_PLACE_CODE"] == (
        "outboundShippingPlaceCode", "shippingPlaceCode",
        "outboundShippingPlaceId", "placeCode")


def test_the_raw_keys_are_what_the_picker_offers():
    """보기의 출처는 **응답 원문**이다 — 우리가 만든 목록이 아니다."""
    src = _render_lookup_source()
    assert "e.raw" in src and "data-lk-manual" in src
    assert json.dumps(DATA)  # 이 계약이 쓰는 모양이 실측 모양임을 문서화
