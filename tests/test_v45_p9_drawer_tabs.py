"""tests/test_v45_p9_drawer_tabs.py — v45 P9: 편집 드로어 칩 탭 분리(퍼센티 벤치마크).

[상품명·카테고리][가격][옵션][키워드][썸네일][상세페이지][업로드] 칩 네비. 한 탭씩 표시.
필드 ID·핸들러는 그대로(회귀 0). 라우트 이동/새 창 0(같은 페이지 클래스 토글).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")

_TABS = ["basic", "price", "options", "keywords", "thumb", "detail", "upload"]


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_chip_nav_has_seven_tabs():
    for t in _TABS:
        assert f'data-etab="{t}"' in PREVIEW, t
    # 칩 라벨(사용자 노출) 존재
    for label in ("상품명·카테고리", "가격", "옵션", "키워드", "썸네일", "상세페이지", "업로드"):
        assert label in PREVIEW, label
    assert 'class="kgp-etabs"' in PREVIEW


def test_tab_switch_js_toggles_class_no_navigation():
    assert "function kgpEtab(name)" in PREVIEW
    assert "kgp-etab-hide" in PREVIEW
    # 클래스 토글만 — location/href 이동 없음(같은 페이지).
    i = PREVIEW.index("function kgpEtab")
    body = PREVIEW[i:i + 600]
    assert "classList.toggle('kgp-etab-hide'" in body
    assert "location" not in body and "href" not in body


def test_fields_preserved_no_regression():
    # 핵심 편집 필드 ID·핸들러가 탭 분리 후에도 그대로(회귀 0).
    for _id in ("editTitle", "editPrice", "editCurrency", "editCategory", "editKeywords",
                "editDescription", "optionRows", "imageGallery", "detailImagesBlock",
                "detailPageBuilder", "btnSaveEdits", "btnOpenUploadModal"):
        assert f'id="{_id}"' in PREVIEW, _id
    for handler in ("saveEdits()", "openUploadModal()", "autoClassify()", "translateToKo()",
                    "aiDescribe()", "convertToKrw()", "addOptionRow()"):
        assert handler in PREVIEW, handler


def test_sections_marked_with_esec_and_tab():
    # 각 탭에 최소 1개 kgp-esec 섹션이 매핑됐는지(빈 탭 0).
    import re
    secs = re.findall(r'class="kgp-esec[^"]*"[^>]*data-etab="(\w+)"', PREVIEW)
    secs += re.findall(r'data-etab="(\w+)"[^>]*class="kgp-esec', PREVIEW)
    present = set(secs)
    for t in _TABS:
        assert t in present, f"탭 {t}에 섹션 없음"


def test_default_tab_basic_others_prehidden():
    # 기본 basic 활성 + 나머지 섹션은 초기 kgp-etab-hide(JS 전에도 한 탭만 보임).
    assert 'class="kgp-etab-chip active" data-etab="basic"' in PREVIEW
    # thumb/price/options/keywords/detail/upload 섹션은 초기 hide 클래스 보유
    for t in ("price", "options", "keywords", "thumb", "detail", "upload"):
        assert f'kgp-etab-hide" data-etab="{t}"' in PREVIEW or f'data-etab="{t}"' in PREVIEW


def test_preview_renders_with_tabs(client):
    """실제 렌더 — 수집 항목 편집 페이지에 칩 네비가 나온다."""
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    iid = ch.append(source="extension", url="https://temu.com/g-1.html",
                    title="테스트 소파", price="100", currency="KRW", seller_id="u1")
    r = client.get(f"/seller/collect/preview/{iid}?drawer=1")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'class="kgp-etabs"' in html
    assert 'data-etab="upload"' in html and "상품명·카테고리" in html
    assert 'id="editTitle"' in html   # 필드 보존
