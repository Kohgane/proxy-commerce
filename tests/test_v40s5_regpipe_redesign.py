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
    """Stage 5 CSS **선언부만**. 주석은 근거로 값을 인용할 수 있으므로 제외한다(하드코딩과 구분)."""
    css = CSS.read_text(encoding="utf-8")
    block = css.split("v2 Stage 5-b")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


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
    # 5-b에서 표면은 **soft 계열**로 이관됐다(부드럽게 — 오너 피드백).
    for token in ("--font-display", "--nm-soft", "--nm-soft-in", "--space-", "--radius",
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


def test_zone_hierarchy_present():
    """레이아웃 구획 — **번호 붙은 4존**(입력·결과·검수표·등록)이 배경 톤 교차로 갈린다.

    오너 1차 피드백("레이아웃 좀 더 확실하게 드러나게") 반영: Step 1/2 문구 → 존 번호 01~05.
    """
    html, css = _tpl(), _s5_css()
    for num in ("01", "02", "03", "04", "05"):
        assert f'rp-zone-num">{num}<' in html, num
    assert html.count("rp-zone-alt") == 2                # 교차 밴드 2개(결과·등록)
    assert html.count("rp-zone-head") == 5
    assert "rp-kpis" in html and html.count("rp-kpi-value") == 4
    # 밴드는 배경 톤으로 갈린다(보더 아님) + 섹션 여백은 토큰(5-d: 48 → 32px, 오너 D3 지시).
    assert "color-mix" in _block(css, ".rp-zone-alt")
    assert "--space-6" in _block(css, ".rp-zone")


def test_soft_neumorphism_tokens():
    """오너 1차 피드백("좀 더 부드럽게") — 넓은 블러·낮은 알파·큰 라운드."""
    css = CSS.read_text(encoding="utf-8")
    root = css.split("--nm-soft:")[1].split(";")[0]
    assert "24px" in root                                  # 블러 반경 ↑(기존 16px)
    assert ".055" in root or ".05" in root                 # 알파 ↓(기존 .09)
    s5 = _s5_css()
    for surface in (".rp-hero", ".rp-kpi", ".rp-table-card"):
        assert "--nm-soft" in _block(s5, surface), surface
        assert "--radius-2xl" in _block(s5, surface), surface
    assert "--radius-2xl: 22px" in css                     # 18 → 22


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


# ── Stage 5-c: 오너 판정 후 마이크로패치(존 48px · 디스플레이 타이포 1단 축소) ─────────
#    → **5-d가 승계**(오너 D2·D3): 최신 지시가 이긴다. 5-c 수치는 아래 주석에 근거로만 남긴다.
def test_stage5d_one_screen_ingredients():
    """★ D1 좌표계 = **1920×940**(1080 모니터 − 브라우저 크롬). 섹션 01+02가 한 화면.

    실측(scripts/_devshot_v40s5d.py, 헤드리스 크로뮴):
      5-c: KPI 하단 1,075px / 940px → **135px 초과**
      5-d: KPI 하단   927px / 940px → **한 화면 O(여유 13px)**
    CSS는 그 결과를 만든 재료만 못박는다 — 픽셀 판정은 devshot이 한다(캡처가 산출물).
    """
    css = _s5_css()
    # D2 — 디스플레이 타이포 추가 1단(32.0 → 27.2px). 부제도 이번엔 1단 허용.
    assert "clamp(1.4rem, 2.7vw, 1.7rem)" in _block(css, ".rp-step-title")
    assert ".88rem" in _block(css, ".rp-step-lead")
    # KPI 숫자는 **계속 불변** — 주인공은 숫자다(축소가 전역으로 번지지 않았음을 못박는다).
    assert "clamp(2.4rem, 4.4vw, 3.2rem)" in _block(css, ".rp-kpi-value")
    assert "1.05rem" in _block(css, ".rp-num")
    # D3 — 잔여 px는 **여백에서만**. 존·카드 안쪽 여백 1스텝.
    assert "var(--space-6) 0" in _block(css, ".rp-zone")
    assert "padding: var(--space-6)" in _block(css, ".rp-hero")


def test_stage5d_textarea_rows_preserved():
    """D3 계약: 입력 줄 수(rows=5)는 **기능 보존** — 여백을 깎아도 여기는 건드리지 않는다."""
    assert 'rows="5"' in _tpl()


def test_stage5c_style_source_is_single():
    """A4: 이 화면 스타일 소스는 **단일**(app.css) — 페이지별 CSS·인라인 색 지정 0."""
    import subprocess
    css_files = subprocess.run(["grep", "-rl", "--include=*.css", ".rp-zone", "src/"],
                               capture_output=True, text=True).stdout.split()
    assert css_files == ["src/static/app.css"], css_files
    html = _tpl()
    assert "color:" not in html and "background:" not in html and "<style" not in html
