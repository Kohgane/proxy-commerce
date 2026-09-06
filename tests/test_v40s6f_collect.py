"""tests/test_v40s6f_collect.py — 디자인 v3 Stage 6-f: 상품 수집(manual_collect).

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 규율뿐 — 카드 문법 승계 · 색 유틸 정리 · 로직 불변.

앞선 슬라이스와 결이 다르다: **이 화면엔 템플릿 스타일 블록이 없었다.**
철거할 게 아니라 v2 카드 5장을 op-card로 옮기고 부트스트랩 색 유틸 17개를 정리하는 게 본론.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates/manual_collect.html")
CSS = Path("src/static/app.css")

_HARDCODED = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\d+px")
_STYLE_OPEN = "<" + "style"


def _t() -> str:
    return TPL.read_text(encoding="utf-8")


def _markup() -> str:
    """주석을 걷어낸 마크업만 — 주석은 옛 값을 근거로 인용하므로 스캔 대상이 아니다."""
    s = re.sub(r"\{#.*?#\}", "", _t(), flags=re.S)
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _s6f_css() -> str:
    block = CSS.read_text(encoding="utf-8").split("Stage 6-f: 상품 수집")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_no_style_block_and_no_inline_hardcoding():
    """스타일 소스는 app.css 하나 — 이 화면은 블록이 원래 0이라 **되살아나지 않는 것**이 계약이다."""
    assert _STYLE_OPEN not in _t()
    bad = [x for x in re.findall(r'style="([^"]*)"', _t()) if _HARDCODED.search(x)]
    assert not bad, f"인라인 하드코딩 잔존: {bad[:3]}"


def test_v2_cards_are_gone():
    """v2 카드 5장 → op-card. 카드 안에 카드를 겹치지 않는다."""
    m = _markup()
    assert '<div class="card ' not in m and '<div class="card">' not in m
    assert "console-card" not in m and "console-step-card" not in m
    assert m.count("<section") == m.count("</section>") == 5
    for part in ("op-card-head", "op-card-body", "op-card-foot"):
        assert part in m, part


def test_actions_live_in_card_footers():
    """액션은 카드 푸터 — 단계마다 '다음에 뭘 누르나'가 한 자리에 있다."""
    m = _markup()
    for btn in ('id="extractBtn"', 'id="bulkCollectBtn"', 'id="uploadBtn"', 'id="saveBtn"'):
        seg = m.split(btn)[0]
        assert seg.rfind("op-card-foot") > seg.rfind("op-card-body"), f"{btn}이 푸터 밖에 있다"


def test_one_filled_button_per_step():
    """★ 단계가 넷이라 **단계마다 채운 버튼 1개**가 규율이다.

    실측: `btn-outline-primary`가 소싱처 칩·현지화·확장 안내에 8개 흩어져
    **어느 것이 다음 행동인지 안 읽혔다.** 칩은 이동 수단이지 행동이 아니다.
    """
    m = _markup()
    assert "btn-outline-primary" not in m and "btn-outline-secondary" not in m
    # 채운 버튼은 단계 CTA 셋(미리보기·일괄수집·업로드)뿐.
    assert len(re.findall(r"btn btn-primary", m)) == 3


def test_source_chips_are_navigation_not_action():
    """소싱처 칩은 마켓으로 **가는** 수단이다 — 버튼 위계에서 빼고 알약으로."""
    m = _markup()
    assert "mc-chip" in m and "mc-chips" in m
    css = _s6f_css()
    chip = css.split(".mc-chip {")[1].split("}")[0]
    assert "border-radius: 999px" in chip and "min-height: 44px" in chip


def test_market_tiles_are_touchable_and_honest():
    """마켓 타일 — 터치 타깃 44px, **미연동은 눌러도 안 되는 자리라고 커서로도 말한다**(죽은 버튼 0)."""
    css = _s6f_css()
    tile = css.split(".mc-market {")[1].split("}")[0]
    assert "min-height: 44px" in tile and "cursor: pointer" in tile
    assert ".mc-market:has(input:disabled)" in css and "cursor: not-allowed" in css
    assert ".mc-market:has(input:checked)" in css      # 고른 게 보인다


def test_toast_uses_the_shared_component():
    """★ 부트스트랩 컬러 토스트를 걷어내고 공통 `pcToast`로 — 토큰 단일 소스.

    호출부 16곳 시그니처는 그대로 두고 **정의 한 곳만** 갈았다(훅을 건드리면 로직 변경).
    """
    m = _markup()
    assert 'id="uploadToast"' not in m and "bootstrap.Toast" not in m
    assert "text-bg-danger" not in m and "text-bg-success" not in m
    shim = m.split("function showToast")[1].split("\n}")[0]
    assert "pcToast(" in shim
    assert "console.log" in shim, "pcToast 미로드 시 조용히 삼키면 실패가 사라진다"
    # pcToast는 textContent로 그린다 — 마크업은 줄바꿈으로 바꿔 넘긴다.
    assert "<br" in shim and "replace(" in shim


def test_no_admin_paths_on_user_screen():
    """★ 일반 유저에게 관리자 경로를 보여주지 않는다(절대원칙).

    번역 미설정 안내가 `/admin/diagnostics`를 그대로 노출하고 있었다 —
    셀러가 열 수 없는 주소이고, 열 수 없는 곳을 가리키는 안내는 안내가 아니다.
    """
    m = _markup()
    assert "/admin/" not in m.replace('{% if _user_role ==', "\x00")  # 관리자 게이트 안은 예외
    assert "번역이 아직 준비되지 않았어요" in m


def test_logic_untouched_hooks_survive():
    """★ 로직 변경 0 — JS가 잡는 훅 25개는 이름 그대로여야 한다."""
    m = _t()
    for hook in ('id="productUrl"', 'id="extractBtn"', 'id="urlError"', 'id="bulkUrls"',
                 'id="bulkCollectBtn"', 'id="bulkResult"', 'id="loadingSpinner"',
                 'id="errorAlert"', 'id="previewCard"', 'id="sourceBadge"',
                 'id="extractedCards"', 'id="titleKo"', 'id="priceOriginal"',
                 'id="currencyLabel"', 'id="targetLocales"', 'id="localizeBtn"',
                 'id="localizedPreview"', 'id="saveBtn"', 'id="uploadBtn"',
                 'id="oneclickCard"', 'id="oneclickMarkets"',
                 "market-checkbox", "localized-title", "localized-description",
                 "data-amazon-dropdown", "data-amazon-country", 'id="step-1"'):
        assert hook in m, f"훅 소실: {hook}"


def test_step_handlers_unchanged():
    """단계 표시·핸들러 이름 불변 — 화면만 바뀌고 흐름은 그대로다."""
    m = _t()
    for fn in ("extractProduct()", "bulkCollect()", "localizeProduct()",
               "saveToSheets()", "uploadProduct()", "setStep("):
        assert fn in m, fn


def test_no_emoji_on_user_screen():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    found = emoji.findall(_markup())
    assert not found, f"이모지 {found[:5]}"


def test_table_grammar_not_redefined_here():
    """표 정렬 문법(6-e-2)을 화면 슬라이스가 다시 정하지 않는다 — 규칙은 한 곳뿐이다."""
    css = _s6f_css()
    assert "tabular-nums" not in css and "text-overflow: ellipsis" not in css


def test_screen_renders():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    assert app.test_client().get("/seller/collect").status_code == 200
