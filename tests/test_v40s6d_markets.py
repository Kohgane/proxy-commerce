"""tests/test_v40s6d_markets.py — 디자인 v3 Stage 6-d: 마켓 3종(현황·연결·발급 가이드).

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 규율뿐 — 템플릿 스타일 블록 0 · 인라인 하드코딩 0 · 6-a 문법 승계 ·
S1~S3 회귀 0 · 로직 불변.
"""
from __future__ import annotations

import re
from pathlib import Path

MK = Path("src/seller_console/templates/markets.html")
MC = Path("src/seller_console/templates/markets_connect.html")
MG = Path("src/seller_console/templates/markets_guide.html")
CSS = Path("src/static/app.css")
VIEWS = Path("src/seller_console/views.py")

_HARDCODED = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\d+px")
_STYLE_OPEN = "<" + "style"          # 자기 자신을 잡지 않게 조립한다


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _markup(p: Path) -> str:
    """주석을 걷어낸 마크업만 — 주석은 **옛 값을 근거로 인용**하므로 스캔 대상이 아니다.

    (6-c에서 실제로 났던 오탐: 변경 근거를 적은 주석의 hex를 잔재로 잡았다.)
    """
    s = re.sub(r"\{#.*?#\}", "", _t(p), flags=re.S)
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def _s6d_css() -> str:
    """Stage 6-d 슬라이스 선언부만(주석은 옛 값을 근거로 인용할 수 있어 제외)."""
    block = _t(CSS).split("Stage 6-d: 마켓 3종")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_no_style_blocks_left_in_templates():
    """★ 템플릿 스타일 블록 철거 — 스타일 소스는 app.css 하나다(오너 공통 계약).

    이관 전 실측: 연결 1장(mc-*) · 가이드 1장(guide-*) = **2장**.
    """
    for p in (MK, MC, MG):
        assert _STYLE_OPEN not in _t(p), f"{p.name}에 스타일 블록 잔존"


def test_no_hardcoded_hex_or_px_inline():
    """★ 인라인 hex/px 0 — 토큰 단일 소스(디자인 절대원칙)."""
    for p in (MK, MC, MG):
        bad = [s for s in re.findall(r'style="([^"]*)"', _t(p)) if _HARDCODED.search(s)]
        assert not bad, f"{p.name}: {bad[:3]}"


def test_illustration_colors_are_not_baked_into_svg():
    """★ SVG `fill="#..."`는 프레젠테이션 속성이라 var()를 못 받는다 — 그래서 hex가 눌러앉았다.

    가이드 일러스트가 부트스트랩 파랑(#0d6efd)·초록(#198754) 팔레트였다. 색은 CSS에서만 준다.
    """
    g = _markup(MG)
    assert not re.findall(r'(?:fill|stroke)="#', g), "가이드 SVG에 하드코딩 색 잔존"
    css = _s6d_css()
    for cls in (".gi-frame", ".gi-slot", ".gi-cta", ".gi-ok", ".gi-arrow"):
        assert cls in css, f"{cls} 선언 없음"


def test_one_class_attribute_per_tag():
    """클래스 속성이 한 태그에 둘이면 뒤엣것이 **조용히 무시된다**(6-c에서 실제로 났던 사고)."""
    for p in (MK, MC, MG):
        dup = re.findall(r'<[a-zA-Z][^<>]*?class="[^"]*"[^<>]*?class="[^"]*"[^<>]*>', _t(p))
        assert not dup, f"{p.name}: class 중복 {len(dup)}건"


def test_inherits_6a_card_grammar():
    """6-a 문법 승계 — 카드 1장에 헤더/바디/푸터, 조각마다 카드 금지, v2 카드 잔재 0."""
    for p in (MK, MG):
        s = _t(p)
        assert "op-card" in s and "op-card-head" in s and "op-card-body" in s, p.name
        assert '<div class="card ' not in s and '<div class="card">' not in s, p.name
    mk = _t(MK)
    assert mk.count("<section") == mk.count("</section>") == 3   # 연동상태 · 등록현황 · 목록


def test_market_tiles_are_not_aspect_locked():
    """★ 6-c 실측 승계: 담기는 줄 수가 마켓마다 다르다 — 비율을 고정하면 잘리거나 빈다.

    6-a `.op-tile`은 정사각(1:1)이라 진단 문구 4줄 + 버튼 4개가 들어가지 않는다.
    """
    css = _s6d_css()
    tile = css.split(".mk-tile {")[1].split("}")[0]
    assert "aspect-ratio" not in tile, "마켓 타일에 비율 고정 — 진단 문구가 잘린다"
    assert "aspect-ratio" not in css.split(".mk-counts")[0].split(".mk-grid {")[1].split("}")[0]


def test_signal_is_one_geometric_point():
    """Bauhaus 배분 — 상태는 기하 1점. **원색(주황)은 실패에만.**"""
    css = _s6d_css()
    assert '.mk-tile[data-market-state="connected"]::after' in css
    assert "var(--orange)" in css.split('.mk-tile[data-market-state="connected"]')[1][:400]
    # 정상 연결은 청록 — 원색이 아니다(신호 인플레 금지)
    assert "var(--teal)" in css.split('.mk-tile[data-market-state="connected"]::after')[1][:120]


def test_drawer_is_the_glass_surface():
    """Glass는 오버레이에만 — 연결 드로어가 이 화면의 유일한 유리 표면이다."""
    css = _s6d_css()
    drawer = css.split(".mc-drawer {")[1].split("}")[0]
    assert "backdrop-filter" in drawer
    # 카드·타일은 유리가 아니다
    assert "backdrop-filter" not in css.split(".mk-tile {")[1].split("}")[0]


def test_touch_targets_44px():
    """터치 타깃 44px — 6-a가 전 폭에 건 규율."""
    css = _s6d_css()
    assert css.count("min-height: 44px") >= 4


def test_logic_untouched_hooks_survive():
    """★ 로직 변경 0 — JS가 잡는 훅은 이름 그대로여야 한다(개명이 곧 로직 변경).

    이관 중 클래스만 바꾸다 훅을 함께 갈아 화면이 죽는 사고가 이 프로젝트에서 반복됐다.
    """
    mk = _t(MK)
    for hook in ("data-market-card", "data-market-badge", "data-market-summary",
                 "data-market-hint", "data-market-checked-at", "data-market-steps",
                 "data-market-disabled-reason", "data-market-action",
                 'id="marketDiagnosticsSummary"', 'id="marketDiagnosticsDetail"',
                 'id="filterMarket"', 'id="filterStatus"', 'id="rowCount"',
                 'id="syncTime"', 'id="syncAgo"', 'id="productTableBody"'):
        assert hook in mk, f"markets.html 훅 소실: {hook}"
    mc = _t(MC)
    for hook in ("mc-market-nav", "mc-market-col", "mc-drawer-form", "mc-open-drawer",
                 "mc-panel", "mc-dot", "mc-badge", 'id="mcDrawer"', 'id="mcDrawerOverlay"',
                 'id="mcDrawerTitle"', 'id="serverIp"', 'data-role="status-badge"'):
        assert hook in mc, f"markets_connect.html 훅 소실: {hook}"


def test_connect_drawer_class_names_kept_in_css():
    """이관해도 이름은 그대로 — JS가 `.classList.add('open')`으로 잡는 상태 클래스들."""
    css = _s6d_css()
    for sel in (".mc-panel.active", ".mc-drawer.open", ".mc-drawer-overlay.open",
                ".mc-nav-item.active", ".mc-badge.on", ".mc-dot.on"):
        assert sel in css, f"{sel} 선언 없음 — 이관 중 상태 클래스가 사라졌다"


def test_no_emoji_on_user_screen():
    """사용자 화면 이모지 0(절대원칙) — 가이드가 마켓 아이콘을 이모지로 찍고 있었다."""
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    for p in (MK, MC, MG):
        found = emoji.findall(_markup(p))
        assert not found, f"{p.name}: 이모지 {found[:5]}"


# ── S1~S3 회귀 ───────────────────────────────────────────────────────────────
def test_s2b_guide_uses_single_ip_source():
    """★ S2-b 회귀: 가이드가 'Render 아웃바운드 3개 전부 등록'을 그대로 안내하고 있었다.

    게이트 마켓(쿠팡·스마트스토어)은 릴레이 고정 IP **하나**다. 공유 대역을 적는 게 재발 지뢰였다.
    두 화면이 같은 소스(`_connect_ip_ctx` → `allowlist_ips`)를 봐야 값이 갈리지 않는다.
    """
    g = _markup(MG)
    assert "Outbound IP Addresses" not in g, "Render 공유 대역 안내 잔존(재발 지뢰)"
    assert "allowlist_ips" in _t(MG) and "고정 IP" in g
    v = _t(VIEWS)
    guide_fn = v.split("def markets_guide()")[1].split("\ndef ")[0]
    assert "_connect_ip_ctx()" in guide_fn, "가이드가 IP 컨텍스트를 따로 만들고 있다(이중 구현)"


def test_s1_s3_untouched_by_this_slice():
    """S1(단일 연결 판정)·S3(신호줄)은 이 슬라이스가 건드리지 않는다 — 심볼 생존만 확인."""
    from src.seller_console.market_integration_diagnostics import resolve_market_key
    from src.pipeline.ops_snapshot import linked_markets
    assert callable(resolve_market_key) and callable(linked_markets)
    assert ".op-sig" in _t(CSS)                      # S3 신호줄 스타일 생존


def test_muted_token_is_declared():
    """★ 6-d에서 발견: `--muted`를 쓰는 선언이 8곳인데 **정의가 없었다.**

    정의 없는 var()는 오류가 아니라 그 선언 하나가 조용히 무효가 된다 —
    6-a 마켓 타일의 '미연결 회색 점'이 그래서 아예 안 그려지고 있었다.
    """
    css = _t(CSS)
    root = css.split(":root")[1].split("}")[0]
    assert re.search(r"--muted:\s*#", root), "--muted 선언 없음 — var(--muted) 사용처가 죽는다"


def test_screens_render():
    """세 화면이 실제로 200으로 뜬다(치환 실수로 Jinja가 깨지는 걸 잡는다)."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    for path in ("/seller/markets", "/seller/markets/connect",
                 "/seller/markets/connect/coupang", "/seller/markets/guide"):
        assert c.get(path).status_code == 200, path
