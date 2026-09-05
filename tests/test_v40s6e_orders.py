"""tests/test_v40s6e_orders.py — 디자인 v3 Stage 6-e: 주문 관리.

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 규율뿐 — 스타일 블록 0 · 인라인 하드코딩 0 · 6-a 문법 승계 · 로직 불변.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates/orders.html")
CSS = Path("src/static/app.css")

_HARDCODED = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\d+px")
_STYLE_OPEN = "<" + "style"


def _t() -> str:
    return TPL.read_text(encoding="utf-8")


def _markup() -> str:
    """주석을 걷어낸 마크업만 — 주석은 옛 값을 근거로 인용한다(6-c·6-d에서 반복된 오탐)."""
    s = re.sub(r"\{#.*?#\}", "", _t(), flags=re.S)
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _s6e_css() -> str:
    block = CSS.read_text(encoding="utf-8").split("Stage 6-e: 주문 관리")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_no_style_block_and_no_inline_hardcoding():
    """스타일 소스는 app.css 하나 · 인라인 hex/px 0(토큰 단일 소스)."""
    s = _t()
    assert _STYLE_OPEN not in s
    bad = [x for x in re.findall(r'style="([^"]*)"', s) if _HARDCODED.search(x)]
    assert not bad, bad


def test_inherits_card_grammar():
    """6-a 문법 — 카드 1장에 헤더/바디/푸터, v2 카드 잔재 0."""
    s = _t()
    assert "op-card-head" in s and "op-card-body" in s and "op-card-foot" in s
    assert '<div class="card ' not in s and '<div class="card">' not in s
    assert s.count("<section") == s.count("</section>")


def test_bulk_actions_live_in_the_card_footer():
    """일괄 액션은 카드 푸터다(6-c가 세운 자리) — 헤더에 흩어 놓지 않는다."""
    s = _t()
    foot = s.split('<div class="op-card-foot">')[1].split("</div>\n  </section>")[0]
    for btn in ("bulkTrackingButton", "bulkShipButton", "bulkStatusButton", "export.csv"):
        assert btn in foot, f"{btn}이 푸터에 없다"


def test_stat_tiles_are_not_aspect_locked():
    """6-c 실측 승계 — 12열 폭에서 비율 고정은 목록을 첫 화면 밖으로 민다."""
    css = _s6e_css()
    tile = css.split(".od-stat {")[1].split("}")[0]
    assert "aspect-ratio" not in tile


def test_zero_does_not_light_the_signal():
    """★ 0이면 신호를 켜지 않는다 — 없는 일을 붉게 칠하지 않는다(정직 표기).

    반품/교환 0건인데 주황 점이 켜져 있으면 매일 아침 없는 일을 확인하게 된다.
    """
    css = _s6e_css()
    assert ".od-stat.is-zero::after { display: none; }" in css
    m = _markup()
    assert "'is-alert' if kpi.returned_exchanged else 'is-alert is-zero'" in m
    assert "'is-on' if kpi.today_new else 'is-on is-zero'" in m


def test_primary_color_is_one_signal():
    """원색(주황)은 조치가 필요한 하나에만 — 신규는 청록(정상 유입)."""
    css = _s6e_css()
    on = css.split(".od-stat.is-on::after, .od-stat.is-alert::after {")[1].split("}")[0]
    assert "var(--teal)" in on
    # 결합 선택자(`.is-on::after, .is-alert::after`)가 먼저 걸리지 않게 **줄 시작**을 본다.
    alert = css.split("\n.od-stat.is-alert::after {")[1].split("}")[0]
    assert "var(--orange)" in alert


def test_row_actions_keep_their_density():
    """★ 44px는 **카드 밖·헤더 조작 요소**에만. 표 안 행 액션까지 키우면 행이 두 배가 된다.

    6-d는 `.mk-page .btn` 전체에 걸었다 — 목록이 본론인 이 화면에선 밀도가 기능이라
    같은 규칙을 그대로 승계하지 않는다(근거 있는 분기).
    """
    css = _s6e_css()
    assert ".od-page .btn { min-height: 44px" not in css
    assert ".od-page .op-card-head .btn { min-height: 44px; }" in css
    assert ".od-page .form-select, .od-page .form-control, .od-page .op-card-foot .btn" in css


def test_health_strip_only_when_unhealthy():
    """★ 경보 피로 방지 — '정상입니다' 줄이 상시로 있으면 진짜 503도 안 읽힌다."""
    m = _markup()
    assert "{% if not ops_health.service_available %}" in m
    assert "주문 운영 라우트 상태: 정상" not in m


def test_logic_untouched_hooks_survive():
    """로직 변경 0 — JS가 잡는 훅은 이름 그대로여야 한다."""
    s = _t()
    for hook in ('id="ordersSyncButton"', 'id="sync-spinner"', 'id="ordersSelectAll"',
                 'id="bulkSelectionCount"', 'id="bulkActionHint"', 'id="bulkTrackingButton"',
                 'id="bulkShipButton"', 'id="bulkStatusButton"', 'id="trackingModal"',
                 'id="bulkTrackingModal"', 'id="tm-courier"', 'id="tm-courier-listbox"',
                 "order-row-chk", "data-order-row=", "data-order-feedback=",
                 "syncNow()", "openTrackingModal(", "openBulkTrackingModal()",
                 "bulkUpdateSelectedStatus(", "kgpCopyOrder(", "kgpToggleSourced("):
        assert hook in s, f"훅 소실: {hook}"


def test_copy_that_pins_protect_survives():
    """★ 6-d 교훈 승계: 핀이 지키는 사용자 카피를 이관하며 지우지 않는다.

    (6-d에서 새로고침 버튼을 지웠다가 i18n 핀이 잡았다. 같은 실수를 두 번 하지 않는다.)
    """
    s = _t()
    assert "주문·배송 관리 화면" in s
    assert "주문 서비스가 일시적으로 준비되지 않았습니다(503)." in s
    assert "CSV 내보내기 (서비스 준비 중)" in s


def test_no_emoji():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    assert not emoji.findall(_markup())


def test_stat_component_debt_is_declared():
    """★ 숫자 타일이 셋(ch·mk·od)이 됐다 — 숨기지 말고 부채로 적어 둔다.

    지금 합치려면 채점 끝난 두 화면을 건드려야 해서 6-j로 미뤘다.
    이 계약이 '넷째를 만들지 말라'는 브레이크다.
    """
    block = CSS.read_text(encoding="utf-8").split("Stage 6-e: 주문 관리")[1].split("*/")[0]
    assert "6-j" in block and ".ch-stat" in block and ".mk-count" in block


def test_screen_renders():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    assert c.get("/seller/orders").status_code == 200
    assert c.get("/seller/orders?status=shipped&search=zzz").status_code == 200
