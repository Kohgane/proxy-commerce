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
    # 선택자 **시작 경계**를 본다 — `.rp-scroll` 검색이 `.rp-card > .rp-scroll`에 걸리면
    # 엉뚱한 블록을 검사하게 된다(5-f에서 실제로 그랬다).
    m = re.search(r"(?:^|\n)\s*" + re.escape(selector) + r"\s*(?:,[^{]*)?\{([^}]*)\}", css)
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
    """입력 줄 수는 **기능 보존** — 여백을 깎아도 여기는 건드리지 않는다.

    5-d는 rows=5였고 **5-g가 6으로 올렸다**(H6: 최소 6줄). JS가 자라게 하기 전의 바닥값이다.
    """
    assert 'rows="6"' in _tpl()


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
    """내부 스크롤 **레이아웃 영역**은 `.rp-scroll` 하나뿐이다(E1 — 스크롤 2곳 금지).

    **5-g 승계(H6):** textarea는 예외다. 50개를 넣으면 그 안에서 스크롤하라는 게 지시이고,
    폼 컨트롤의 자체 스크롤은 레이아웃 영역이 아니다 — 화면이 두 군데로 갈리지 않는다.
    """
    css = _s5_css()
    decls = re.findall(r"\.rp-[a-z-]+[^{]*\{[^}]*overflow-y:\s*(?:auto|scroll)", css)
    layout = [d for d in decls if ".rp-input" not in d]
    assert len(layout) == 1, layout
    assert any(".rp-input" in d for d in decls), "textarea 내부 스크롤이 사라졌다"


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


# ── Stage 5-f: 공동 제거·비율 교정 (오너 F1~F5) ───────────────────────────────
def test_stage5f_column_ratio_and_fill():
    """★ F1 — 좌 32 / 우 68. 5-e는 `minmax(340px,24rem)`이라 1920에서 24/76이었고 나머지가 공동.

    실측(scripts/_devshot_v40s5f.py): 5-e 공동 좌 167px·우 924px → 5-f **좌 0 / 우 0**(0·1·30행 전부).
    """
    css = _s5_css()
    shell = _block(css, ".rp-shell")
    assert "32fr 68fr" in shell
    # 카드가 열 높이를 끝까지 쓴다 → 카드 밖 공동이 생기지 않는다.
    assert "flex: 1 1 auto" in _block(css, ".rp-pane-in .rp-hero")
    assert "flex: 1 1 auto" in _block(css, ".rp-card")


def test_stage5g_textarea_grows_with_content():
    """★ **5-g 승계(H6)** — F2의 "잔여 높이 전부 / 21줄" 계약은 폐기됐다.

    빈 입력칸이 카드를 세로로 다 채우면 **쓰지도 않은 공간이 입력칸 행세**를 한다.
    대신 줄 수만큼 자란다: 최소 6줄 · 최대 카드 잔여 높이(넘치면 그 안에서 스크롤).
    """
    css, html = _s5_css(), _tpl()
    ta = _block(css, ".rp-pane-in .rp-input")
    assert "flex: 0 1 auto" in ta                     # 더는 남는 높이를 다 먹지 않는다
    assert "max-height: 100%" in ta and "overflow-y: auto" in ta
    assert "min-height: calc(6 *" in ta               # 최소 6줄(선언한 행간에서 파생)
    assert 'rows="6"' in html                         # JS 전에도 6줄
    # 높이 계산은 **한 곳**뿐이다 — CSS는 한계만 준다(이중 구현 금지).
    assert html.count("function kgpAutoGrow") == 1 and 'oninput="kgpAutoGrow(this)"' in html
    assert "field-sizing" not in css, "높이 계산이 CSS·JS 두 곳에 생겼다"


def test_stage5g_content_stacks_from_top():
    """H7 — 카드 껍데기는 격자를 채우고(stretch), 내용은 위에서 쌓이고, 나머지는 면이다.

    안내문·[검수표 만들기]는 textarea **바로 아래**에 붙는다(카드 바닥 고정 해제).
    """
    css = _s5_css()
    hero = _block(css, ".rp-pane-in .rp-hero")
    assert "flex: 1 1 auto" in hero                   # 껍데기는 열 높이를 채운다
    assert "justify-content: flex-start" in hero      # 내용은 위에서 쌓인다
    assert "align-items: stretch" in _block(css, ".rp-shell")   # 좌우 카드 높이 동일


def test_stage5f_right_is_one_card():
    """F3 — 헤더(02)·바디(03)·푸터(04)가 **한 카드**에 붙는다(사이가 배경으로 뚫리지 않게)."""
    html, css = _tpl(), _s5_css()
    assert 'class="rp-card"' in html
    card = _block(css, ".rp-card")
    assert "overflow: hidden" in card and "--nm-soft" in card
    # 안쪽 조각은 자기 그림자·라운드를 버리고 카드 표면에 붙는다.
    for inner in (".rp-card > .rp-strip", ".rp-card > .rp-bar"):
        assert "box-shadow: none" in _block(css, inner), inner
    # **5-g 승계(오너 H1):** 5-f는 빈 영역에 행 가이드라인을 깔았는데, 마지막 행 아래까지
    #   줄이 이어져 **없는 행이 있는 것처럼** 보였다. 빈 영역은 카드 표면 톤 그대로 —
    #   무늬·선·점 0. 경계는 카드 테두리가 이미 준다.
    body = _block(css, ".rp-card > .rp-scroll")
    for gone in ("repeating-linear-gradient", "color-mix", "background-image"):
        assert gone not in body, gone


def test_stage5f_empty_state():
    """F5 — 0행이면 바디 중앙 1줄 안내 + 등록 버튼 disabled(공동이 아니라 '아직 비어 있음')."""
    html = _tpl()
    assert "rp-listempty" in html and "검수표를 만들면 여기에 쌓입니다" in html
    assert "{% if not review.review_pass %}disabled{% endif %}" in html


def test_stage5f_url_is_single_line_without_query():
    """F4 — URL 1줄 말줄임 + 전체는 title 호버. 쿼리스트링은 **서버가 잘라** 보낸다."""
    from src.pipeline.register_pipe import _short_url
    html, css = _tpl(), _s5_css()
    assert 'title="{{ r.url }}"' in html and "r.url_short" in html
    u = _block(css, ".rp-url")
    assert "text-overflow: ellipsis" in u and "white-space: nowrap" in u
    got = _short_url("https://www.amazon.com/dp/B0ABC?ref=sr_1_3&keywords=grip")
    assert got == "www.amazon.com/dp/B0ABC"           # 쿼리 제거·프로토콜 제거
    assert len(_short_url("https://x.com/" + "a" * 200)) <= 60
    # 원본 url은 그대로 남는다(수집·중복키·등록은 전부 원본을 쓴다).
    assert '"url": url' in Path("src/pipeline/register_pipe.py").read_text(encoding="utf-8")


def test_stage5f_mobile_does_not_collapse_textarea():
    """1열로 쌓이면 열 높이가 사라져 `flex:1`이 textarea를 1줄로 짜부한다(실측 48px) — 최소 높이로 되돌린다."""
    css = _s5_css()
    mob = css.split("@media (max-width: 1199.98px)")[1]
    assert "min-height: 11rem" in mob and "flex: 0 0 auto" in mob
