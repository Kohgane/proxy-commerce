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
    for cls in (".rp-step-title", ".rp-stat-v", ".rp-num"):
        assert "--font-display" in _block(css, cls), cls
    assert "clamp(" in _block(css, ".rp-step-title")     # 반응형 디스플레이
    assert "tabular-nums" in css                                        # 숫자 정렬(Swiss)


def test_neumorphism_is_restrained_not_embossed():
    """뉴모피즘은 **카드·입력·버튼 표면에만**. 텍스트 대비를 건드리지 않는다(AA 불변)."""
    css = _s5_css()
    for surface in (".rp-hero", ".rp-strip", ".rp-table-card", ".rp-chip", ".rp-res"):
        assert "box-shadow" in _block(css, surface), surface
    # 그림자는 표면에만 — 텍스트 색을 흐리게 만드는 선언이 없어야 한다.
    assert "text-shadow" not in css
    assert "opacity: .5" not in css and "opacity:.5" not in css


def test_no_thick_borders_and_no_geometry():
    """두꺼운 보더 0(헤어라인만) · Bauhaus 기하 액센트 0(v2 결정)."""
    css = _s5_css()
    assert "width: 1px" in _block(css, ".rp-stat + .rp-stat::before")   # 구획은 헤어라인(박스 아님)
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
    """레이아웃 구획 — **번호 붙은 단계**(01 입력 · 02 결과 · 03 검수표 · 04 등록).

    5-b는 세로 5존 + 배경 톤 교차였다. **5-e가 승계**(오너 E1·E2): 뷰포트 고정 2단 셸이라
    존 밴드가 사라지고 좌/우 배치가 구획을 만든다. 05(수집 실패)는 02 카운트 + 03 접힘으로 갔다.
    """
    html, css = _tpl(), _s5_css()
    for num in ("01", "02", "03", "04"):
        assert f'rp-step-num">{num}<' in html, num
    assert "rp-shell" in html and "rp-pane-in" in html and "rp-pane-work" in html
    assert "rp-strip" in html and html.count("rp-stat-v") == 4      # KPI 4개는 스트립으로
    # E4 — 옛 존/카드 마크업 **잔재 0**(이중 구현 방지).
    for gone in ("rp-zone", "rp-kpis", "rp-kpi-value", "rp-kpi-label"):
        assert gone not in html, gone
    assert "grid-template-columns" in _block(css, ".rp-shell")


def test_soft_neumorphism_tokens():
    """오너 1차 피드백("좀 더 부드럽게") — 넓은 블러·낮은 알파·큰 라운드."""
    css = CSS.read_text(encoding="utf-8")
    root = css.split("--nm-soft:")[1].split(";")[0]
    assert "24px" in root                                  # 블러 반경 ↑(기존 16px)
    assert ".055" in root or ".05" in root                 # 알파 ↓(기존 .09)
    s5 = _s5_css()
    for surface in (".rp-hero", ".rp-strip", ".rp-table-card"):
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
    assert "1.9rem" in _block(css, ".rp-stat-v")        # E3: 카드 크롬은 걷되 숫자 위계는 유지
    assert "1.05rem" in _block(css, ".rp-num")
    # D3 — 잔여 px는 **여백에서만**. 카드 안쪽 여백 1스텝(존은 5-e에서 소멸).
    assert "padding: var(--space-6)" in _block(css, ".rp-hero")


def test_stage5d_textarea_rows_preserved():
    """D3 계약: 입력 줄 수(rows=5)는 **기능 보존** — 여백을 깎아도 여기는 건드리지 않는다."""
    assert 'rows="5"' in _tpl()


def test_stage5c_style_source_is_single():
    """A4: 이 화면 스타일 소스는 **단일**(app.css) — 페이지별 CSS·인라인 색 지정 0."""
    import subprocess
    css_files = subprocess.run(["grep", "-rl", "--include=*.css", ".rp-shell", "src/"],
                               capture_output=True, text=True).stdout.split()
    assert css_files == ["src/static/app.css"], css_files
    html = _tpl()
    assert "color:" not in html and "background:" not in html and "<style" not in html


# ── Stage 5-e: 뷰포트 고정 2단 셸 (오너 E1~E6) ────────────────────────────────
def test_stage5e_viewport_fit_ingredients():
    """★ E1 = 1920×940에서 **body 스크롤바 0**. 내부 스크롤은 03 표 1곳만.

    실측(scripts/_devshot_v40s5e.py, 헤드리스 크로뮴):
      5-d: scrollHeight 2,599 / 940 → body 스크롤 O · 내부 스크롤러 0곳
      5-e: scrollHeight   940 / 940 → **body 스크롤 X** · 내부 스크롤러 **1곳(rp-scroll)**
    CSS는 그 결과를 만든 재료만 못박는다 — 픽셀 판정은 devshot이 한다(캡처가 산출물).
    """
    css = _s5_css()
    shell = _block(css, ".rp-shell")
    assert "grid-template-columns" in shell and "100dvh" in shell        # 뷰포트에 묶인다
    scroll = _block(css, ".rp-scroll")
    assert "overflow-y: auto" in scroll and "min-height: 0" in scroll    # 유일한 스크롤러
    # 조건부 배너가 위에 끼면 고정 calc은 넘친다(실측 72px) → 남는 높이를 먹는 flex로 확정.
    assert "main:has(> .rp-shell)" in css
    # 04는 sticky 흉내가 아니라 **레이아웃상 마지막 칸**이라 항상 바닥에 있다.
    assert "flex: 0 0 auto" in _block(css, ".rp-bar")


def test_stage5e_single_scroller_by_construction():
    """내부 스크롤 선언은 `.rp-scroll` **하나뿐**이어야 한다(E1 — 스크롤 2곳 금지)."""
    css = _s5_css()
    decls = re.findall(r"\.rp-[a-z-]+[^{]*\{[^}]*overflow-y:\s*(?:auto|scroll)", css)
    assert len(decls) == 1, decls


def test_stage5e_touch_targets_and_mobile_breakpoint():
    """E5 — 2단이 1열로 풀린다 + M0-c 실측 3종 수리.

    M0-c(390px) 실측 결함: ①존 밴드가 좌우 2px씩 삐져 가로 스크롤 ②터치 타깃 44px 미만 6개
    ③헤드라인 22.4px로 위계 소실. ①은 존 제거로 소멸, ②③은 여기서 못박는다.
    """
    css = _s5_css()
    # `_block`은 첫 매치를 잡으므로(요약 스타일이 앞에 있다) 규칙 문자열을 그대로 본다.
    assert ".rp-shell select.form-select, .rp-shell .btn { min-height: 44px; }" in css
    assert ".rp-note > summary { min-height: 44px;" in css
    assert "@media (max-width: 1199.98px)" in css            # 2단 → 1열
    assert "clamp(1.55rem, 6vw, 1.7rem)" in css              # 22.4 → 24.8px(본문 대비 위계)
    # 옛 존의 풀블리드 음수 마진(가로 스크롤 근원)이 남아 있지 않다.
    assert "margin-inline: calc(-1 * var(--space-4))" not in css


def test_stage5e_failed_zone_absorbed_not_dropped():
    """옛 05존은 **사라진 게 아니라 옮겨졌다** — 카운트는 02 스트립, 사유는 03 접힘(E2)."""
    html = _tpl()
    assert "수집 실패" in html and "사유 보기" in html
    assert 'class="rp-stat rp-stat-fail"' in html            # 02 스트립의 실패 카운트
    assert html.count("rp-res-fail") >= 1                    # 사유 카드 보존
