"""tests/test_op_card_fade_autopsy.py — 장식이 글자를 지우고 있었다(공통 문법 재부검).

6-h-2에서 스크롤 페이드의 **크기 기여**를 0으로 만들고 이렇게 적었다:
  "넘칠 게 없으면 여백 위에 겹쳐 보이지 않는다(조건 분기 없이 안전)."
그 주석이 그대로 계약이 됐고, **틀렸다.** 6-i 캡처가 반증 후보를 냈고 계측이 확정했다.

실측(페이드 켬/끔 두 렌더의 같은 좌표 픽셀 비교):
  · `::after`는 `content:""`로 **넘침과 무관하게 상시 render** — 크기 기여 0 ≠ 표시 0.
  · `margin-top: -24px`가 페이드를 마지막 자식 박스 **안으로** 끌어들이고, sticky는 부모
    content box를 못 벗어나 패딩으로 내려가지 못한다 → 마지막 줄과 14px 교차.
  · 마지막 줄 글자 픽셀 **9%만 잔존**(91% 지워짐). 소싱 허브·반려 감시 동일.

대안 실측: `animation-timeline: scroll(self block)`은 `CSS.supports` true지만 **의사요소에선
구동되지 않았다**(넘치는 카드에서도 opacity 0). 그래서 차선 — 장식을 없애고 신호는 스크롤바가 진다.

이 계약은 그 판단을 못 박는다. 되살리고 싶으면 **먼저 이 계약을 깨야** 하고, 그때는
'넘칠 때만 보이나 + 글자를 안 지우나'를 증명해야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path("src/static/app.css")


def _decl() -> str:
    """선언부만 — 내가 쓴 부검 주석이 내 계약을 통과시키면 안 된다(같은 자해를 이 스위트에서 반복했다)."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def test_the_fade_that_erased_text_is_gone():
    """★ 마지막 줄을 덮던 장식이 없다. 되살리려면 이 줄부터 지워야 한다."""
    css = _decl()
    assert ".op-card-body::after" not in css, "글자를 지우던 페이드가 되살아났다"


def test_no_negative_margin_decoration_inside_scrollers():
    """★ 근원은 **음수 마진 장식**이다 — 흐름 밖으로 빼려다 콘텐츠 위로 올라탄다.

    같은 수를 다른 이름으로 다시 두면 같은 결함이 다시 난다(카드 몸통은 스크롤 컨테이너다).
    """
    css = _decl()
    body = re.findall(r"\.op-card-body[^{]*\{[^}]*\}", css)
    for rule in body:
        assert "margin-top: calc(var(--space-5) * -1)" not in rule
        assert not re.search(r"margin(-top)?:\s*-", rule), f"음수 마진 장식 부활: {rule[:80]}"


def test_the_signal_is_carried_by_the_scrollbar():
    """★ 장식을 뺀 자리를 **무엇이** 대신하는지 못 박는다 — 슬림 스크롤바(같은 슬라이스 6-h-2).

    스크롤바는 `overflow: auto`라 **넘칠 때만** 그려진다. 페이드와 달리 거짓 신호가 없다.
    """
    css = _decl()
    assert "scrollbar-width: thin" in css
    assert ".op-card-body::-webkit-scrollbar" in css
    # 화살표 0 · 트랙 투명 — 6-h-2가 정한 모양 그대로(무회귀).
    assert "::-webkit-scrollbar-button" in css and "display: none" in css
    assert ".op-card-body::-webkit-scrollbar-track" in css


def test_card_stays_positioned_for_future_overlays():
    """`.op-card { position: relative }`는 남긴다 — 리사이즈 그립(6-h-3)이 이걸 딛고 있다."""
    assert ".op-card { position: relative; }" in _decl()
