"""tests/test_v72b_price_single_source.py — v72b STEP1: 가격 단일 소스(P0).

증상: 수집가가 있는데 드로어 '가격(원가)' 0.00 + 마켓 등록 가격 거부. 근원 = 이원화(price 정본 vs
price_original 파생) + number 입력이 "81800."(꼬리 점) 거부. 수리: canonical_price 단일 소스(price→
price_original 순 정규화)를 드로어·마진·마켓 등록·append 전부 참조. 드로어는 number 입력 전 정규화.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.collectors.collect_sanitize import canonical_price

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


# ── canonical_price 계약 ──
@pytest.mark.parametrize("cands,expected", [
    (("81800.",), "81800"),                 # 꼬리 점(number 입력 거부 근원)
    (("", "81800"), "81800"),               # price 빈값 → price_original 사용
    (("1,234",), "1234"),                    # 콤마
    (("₩81,800", None), "81800"),
    (("29.99",), "29.99"),
    (("", "", ""), ""),                      # 전부 빈값 → '' (0.00 저장 금지)
    (("N/A", "없음"), ""),                    # 파싱 실패 → ''
    ((None, "0", "0.00"), ""),               # 0류 → ''
])
def test_canonical_price(cands, expected):
    assert canonical_price(*cands) == expected, cands


def test_source_contract_single_source():
    # append 3경로(quick·bookmarklet·bulk)가 정본 단일 소스 사용.
    assert "def _canon_price(d)" in VIEWS
    assert VIEWS.count("_canon_price(draft)") >= 2 and "_canon_price(d)," in VIEWS
    # 옛 이원화 표현(price_original 우선) 제거.
    assert 'str(draft.get("price_original") or draft.get("price")' not in VIEWS
    # 마켓 등록도 canonical_price 정규화.
    assert "canonical_price as _cp" in VIEWS
    # 드로어가 정본 순서(price→price_original→item)로 읽고 number 입력 전 정규화.
    assert "_normPriceStr(_firstNonEmpty(_EXTRA.price, _EXTRA.price_original, _ITEM.price" in PREVIEW
    assert "function _normPriceStr(raw)" in PREVIEW


# ── _normPriceStr(드로어) + number 입력 수용 실증 ──
def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_norm_price_str_number_input_accepts():
    """<input type=number>가 "81800."을 거부해 0.00 되던 것 → _normPriceStr 정규화 후 값 채움."""
    from playwright.sync_api import sync_playwright

    m = re.search(r"function _normPriceStr\(raw\) \{.*?\n\}", PREVIEW, re.S)
    assert m, "_normPriceStr 추출 실패"
    fn = m.group(0)
    html = ('<!doctype html><html><body><input type="number" step="0.01" id="p">'
            '<script>' + fn + '</script></body></html>')
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()
        page.set_content(html, wait_until="load")
        out = page.evaluate("""() => {
            const inp = document.getElementById('p');
            const raw = document.createElement('input'); raw.type='number';
            raw.value = '81800.';                      // 원본 오염값 직접 대입 → number 입력이 거부
            const before = raw.value;                  // '' (거부)
            inp.value = _normPriceStr('81800.');        // 정규화 후 대입
            return { before, after: inp.value,
                     comma: _normPriceStr('1,234'), won: _normPriceStr('₩81,800'), bad: _normPriceStr('N/A') };
        }""")
        b.close()
    assert out["before"] == "", out          # 꼬리 점 → number 입력 거부(0.00 근원 재현)
    assert out["after"] == "81800", out      # 정규화 후 값 채움
    assert out["comma"] == "1234" and out["won"] == "81800" and out["bad"] == "", out
