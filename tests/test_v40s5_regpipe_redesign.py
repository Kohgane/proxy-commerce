"""tests/test_v40s5_regpipe_redesign.py — 디자인 v2 Stage 5: register-pipe 전면 재설계.

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 **규율**뿐이다 — 토큰 단일소스·하드코딩 금지·구조 유지·죽은 버튼 0.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates/register_pipe.html")
CSS = Path("src/static/app.css")


def _tpl() -> str:
    return TPL.read_text(encoding="utf-8")


def _s5_css() -> str:
    css = CSS.read_text(encoding="utf-8")
    return css.split("디자인 v2 Stage 5")[1]


def _block(css: str, selector: str) -> str:
    """정확한 선택자의 선언 블록. `.rp-kpi`가 `.rp-kpis`에 먼저 걸리지 않게 경계를 본다."""
    m = re.search(re.escape(selector) + r"\s*(?:,[^{]*)?\{([^}]*)\}", css)
    assert m, f"선택자 없음: {selector}"
    return m.group(1)


def test_no_hardcoded_hex_or_px_in_template():
    """토큰 단일소스 — 템플릿에 색·치수 하드코딩 0(디자인 절대원칙)."""
    html = _tpl()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", html)
    # 인라인 style 자체를 금지하진 않되(테이블 폭 등), 색 지정은 없어야 한다.
    assert "color:" not in html and "background:" not in html


def test_stage5_css_uses_tokens_only():
    """Stage 5 CSS는 **토큰만** 쓴다 — 새 원색·하드코딩 hex 0."""
    css = _s5_css()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "Stage 5 CSS에 하드코딩 hex"
    for token in ("--font-display", "--nm-up", "--nm-in", "--space-", "--radius",
                  "--teal", "--gold", "--danger", "--hairline-color"):
        assert token in css, token


def test_typography_pairing_is_visible():
    """세리프(숫자)×산세리프(본문) 페어링이 **실제 크기 차**로 보이게 — 금속활자 규율."""
    css = _s5_css()
    for cls in (".rp-step-title", ".rp-kpi-value", ".rp-num"):
        assert "--font-display" in _block(css, cls), cls
    assert "clamp(" in _block(css, ".rp-kpi-value")      # 반응형 대형 숫자
    assert "tabular-nums" in css                                        # 숫자 정렬(Swiss)


def test_neumorphism_is_restrained_not_embossed():
    """뉴모피즘은 **카드·입력·버튼 표면에만**. 텍스트 대비를 건드리지 않는다(AA 불변)."""
    css = _s5_css()
    for surface in (".rp-hero", ".rp-kpi", ".rp-table-card", ".rp-chip", ".rp-res"):
        assert "box-shadow" in _block(css, surface), surface
    # 그림자는 표면에만 — 텍스트 색을 흐리게 만드는 선언이 없어야 한다.
    assert "text-shadow" not in css
    assert "opacity: .5" not in css and "opacity:.5" not in css


def test_no_thick_borders_and_no_geometry():
    """두꺼운 보더 0(헤어라인만) · Bauhaus 기하 액센트 0(v2 결정)."""
    css = _s5_css()
    assert "height: 1px" in _block(css, ".rp-kpi::before")   # 3px 띠가 아니라 헤어라인
    for banned in ("border-radius: 50%", "clip-path", "polygon("):
        assert banned not in css, banned


def test_structure_and_handlers_survive():
    """재설계여도 **기능은 그대로** — 죽은 버튼 0, 폼·핸들러·id 보존."""
    html = _tpl()
    for keep in ('id="urls"', 'id="p3Market"', 'id="p3Account"', 'id="p3Result"',
                 'id="p3MarketNote"', 'p3SyncAccounts()', 'p3Register(false)', 'p3Register(true)',
                 'action="/seller/sourcing/register-pipe"'):
        assert keep in html, keep
    # 마켓 3종 유지.
    for m in ('value="coupang"', 'value="smartstore"', 'value="woocommerce"'):
        assert m in html, m


def test_step_hierarchy_present():
    """Swiss 위계 — 단계(Step 1/2)가 화면에서 먼저 읽힌다."""
    html = _tpl()
    assert "Step 1" in html and "Step 2" in html
    assert html.count("rp-step-eyebrow") >= 3            # 입력·등록·실패 섹션
    assert "rp-kpis" in html and html.count("rp-kpi-value") == 4


def test_density_wall_of_text_removed():
    """정보 벽 제거 — 긴 판정 기준은 **접어 두고** 핵심은 칩으로."""
    html = _tpl()
    assert "rp-chip" in html and "<details class=\"rp-note\">" in html
    # 옛 파란 안내 박스 3연벽이 사라졌는지(같은 내용은 칩·접이식으로 이동).
    assert html.count("pc-status-info") == 0


def test_result_cards_are_status_colored():
    """카나리 결과 = 상태별 카드(성공 청록 · 중복 금 · 실패 사유 카드)."""
    html, css = _tpl(), _s5_css()
    for cls in ("rp-res-ok", "rp-res-dup", "rp-res-fail"):
        assert cls in html and cls in css, cls
    assert "--teal" in _block(css, ".rp-res-ok")


def test_honest_data_wording_kept():
    """정직 표기 문구는 재설계에도 살아 있다(가짜 성공·임의 환산 0)."""
    html = _tpl()
    for phrase in ("미입력", "미검증", "마진 미반영", "취급 제외", "실패로 정직하게"):
        assert phrase in html, phrase


def test_reduced_motion_and_mobile():
    """모션 감소·모바일 대응(터치 타깃·표 스택)."""
    css = CSS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css
    s5 = _s5_css()
    assert "@media (max-width: 767.98px)" in s5
    assert "display: none" in s5.split("@media (max-width: 767.98px)")[1]   # 모바일 thead 숨김
