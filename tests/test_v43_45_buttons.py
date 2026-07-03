"""tests/test_v43_45_buttons.py — v43-4 마진 계산기 인라인 모달 + v43-5 원본 보기 새 탭.

4: 마진 계산기 버튼 → 서버 이동 대신 인라인 모달(원가·판매가·수수료·배송비 → 마진율).
5: 원본 보기/원본 페이지 = 새 탭(target=_blank), 외부 URL을 iframe으로 열지 않음.
"""
from __future__ import annotations

from pathlib import Path

PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
HISTORY = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


# ── v43-4 마진 계산기 ──
def test_margin_calc_is_inline_modal_not_page_link():
    # 옛 서버 이동 링크 제거 → 인라인 모달 버튼.
    assert '<a href="/seller/pricing" class="btn btn-outline-primary btn-sm"><i class="bi bi-cash-coin"></i> 마진 계산기</a>' not in PREVIEW
    assert 'onclick="openMarginCalc()"' in PREVIEW
    assert 'id="marginCalcModal"' in PREVIEW


def test_margin_calc_has_inputs_and_outputs():
    for el in ("mcCost", "mcSell", "mcFee", "mcShip", "mcProfit", "mcRate"):
        assert f'id="{el}"' in PREVIEW
    assert "function calcMargin()" in PREVIEW
    # 수식: 판매가 − 원가 − 수수료 − 배송비
    assert "sell - cost - (sell * fee / 100) - ship" in PREVIEW
    # 통화 미상/환율 없음 → 임의 환산 금지(0).
    assert "환율 없으면 0" in PREVIEW or "임의 환산 금지" in PREVIEW


# ── v43-5 원본 보기 새 탭 ──
def test_origin_links_open_new_tab_not_iframe():
    # 드로어 '원본 보기' + 편집 '원본 페이지' 모두 target=_blank.
    assert 'id="kgpDrawerOrigin"' in HISTORY and 'target="_blank"' in HISTORY
    assert 'href="{{ item.url }}" target="_blank"' in PREVIEW
    # 드로어 iframe은 우리 preview(same-origin)만 로드 — 외부 item.url을 iframe src로 절대 안 씀.
    assert "fr.src = '/seller/collect/preview/'" in HISTORY
    assert "fr.src = item.url" not in HISTORY and ".src = url" not in HISTORY
