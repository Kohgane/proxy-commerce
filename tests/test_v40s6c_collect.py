"""tests/test_v40s6c_collect.py — 디자인 v3 Stage 6-c: 수집한 상품 + 편집 드로어.

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 규율뿐 — 템플릿 `<style>` 0 · 인라인 하드코딩 0 · 6-a 문법 승계 · 로직 불변.
"""
from __future__ import annotations

import re
from pathlib import Path

HIST = Path("src/seller_console/templates/collect_history.html")
ROWS = Path("src/seller_console/templates/collect_history_rows.html")
PREV = Path("src/seller_console/templates/collect_preview.html")
CSS = Path("src/static/app.css")

_HARDCODED = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\d+px")


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _s6c_css() -> str:
    """Stage 6-c 슬라이스 선언부만(주석은 옛 값을 근거로 인용할 수 있어 제외)."""
    css = _t(CSS)
    block = css.split("Stage 6-c: 수집한 상품")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_no_style_blocks_left_in_templates():
    """★ 템플릿 `<style>` 철거 — 스타일 소스는 app.css 하나다(오너 공통 계약).

    이관 전 실측: 수집 이력 1장 · 편집 4장 = **5장**이 화면마다 흩어져 있었다.
    """
    for p in (HIST, ROWS, PREV):
        assert "<style" not in _t(p).replace("<style> 철거", ""), f"{p.name}에 <style> 잔존"


def test_no_hardcoded_hex_or_px_inline():
    """★ 인라인 hex/px 0 — 토큰 단일 소스(디자인 절대원칙)."""
    for p in (HIST, ROWS, PREV):
        bad = [s for s in re.findall(r'style="([^"]*)"', _t(p)) if _HARDCODED.search(s)]
        assert not bad, f"{p.name}: {bad[:3]}"


def test_one_class_attribute_per_tag():
    """클래스 속성이 한 태그에 둘이면 뒤엣것이 **조용히 무시된다** — 이관 중 실제로 났던 사고."""
    for p in (HIST, ROWS, PREV):
        dup = re.findall(r'<[a-zA-Z][^<>]*?class="[^"]*"[^<>]*?class="[^"]*"[^<>]*>', _t(p))
        assert not dup, f"{p.name}: class 중복 {len(dup)}건"


def test_inherits_6a_card_grammar():
    """6-a 문법 승계 — 카드 1장에 헤더/바디/푸터, 액션은 푸터, 조각마다 카드 금지."""
    h = _t(HIST)
    assert "op-card" in h and "op-card-head" in h and "op-card-body" in h
    assert "op-card-foot pc-bulk-toolbar" in h        # 일괄 액션 = 카드 푸터
    assert h.count("<section") == h.count("</section>") == 3   # 요약·필터 합본 + 목록 + 빈 목록
    assert '<div class="card ' not in h and '<div class="card">' not in h  # v2 카드 잔재 0


def test_summary_tiles_are_not_aspect_locked():
    """★ 실측이 잡은 것: 12열 폭에서 2:1 타일은 한 칸 190px — 숫자 넷에 260px를 썼다.

    대시보드(5열 카드)와 폭이 달라서 생긴 일이다. 여기선 **높이를 내용이 정한다.**
    """
    block = _s6c_css()
    stats = re.search(r"(?:^|\n)\s*\.ch-stats\s*\{([^}]*)\}", block)
    stat = re.search(r"(?:^|\n)\s*\.ch-stat\s*\{([^}]*)\}", block)
    assert stats and stat
    assert "aspect-ratio" not in stat.group(1), "요약 타일에 비율 고정이 돌아왔다"
    assert "repeat(4" in stats.group(1)


def test_drawer_is_the_glass_surface():
    """v3 배분: Glass는 **오버레이·드로어**가 맡는 자리다(결정문 역할 표)."""
    block = _s6c_css()
    drawer = re.search(r"(?:^|\n)\s*\.kgp-drawer\s*\{([^}]*)\}", block)
    assert drawer and "backdrop-filter" in drawer.group(1)
    back = re.search(r"(?:^|\n)\s*\.kgp-drawer-backdrop\s*\{([^}]*)\}", block)
    assert back and "color-mix" in back.group(1)      # 순흑 rgba가 아니라 먹 토큰


def test_editor_chrome_hiding_is_scoped_to_body_switch():
    """★ 지뢰: 편집기 CSS(`.console-sidebar{display:none}`)를 **무스코프로 전역에 두면**
    모든 화면의 사이드바가 사라진다. `.kgp-editor` 스위치 아래에만 둔다.
    """
    block = _s6c_css()
    for rule in re.findall(r"([^\n{}]+)\{[^}]*display:\s*none\s*!important", block):
        assert ".kgp-editor" in rule or ".kgp-etab-hide" in rule, f"무스코프 숨김: {rule.strip()}"
    assert "{% block body_class %}" in _t(PREV)
    assert 'class="console-body{% block body_class %}{% endblock %}"' in \
        _t(Path("src/seller_console/templates/_base.html"))


def test_logic_untouched_hooks_survive():
    """로직 0 — JS가 잡는 훅(id·클래스·핸들러)이 그대로 있어야 한다."""
    h, prev = _t(HIST), _t(PREV)
    for hook in ("kgpDrawer", "kgpDrawerBackdrop", "closeItemDrawer", "chkAll",
                 "bulkUploadBtn", "excelFile", "fsInfiniteScroll", "kgp-open-drawer"):
        assert hook in h, hook
    for hook in ("kgpLightbox", "kgpLbImg", "addImgPreview", "btnSaveEdits",
                 "btnOpenUploadModal", "kgp-gimg-del", "kgpEtab", "market-tile"):
        assert hook in prev, hook


def test_lightbox_toggle_contract_unchanged():
    """라이트박스는 JS가 **인라인 display**로 여닫는다 — 6-c가 그 계약을 안 바꿨다.

    CSS에 `.show` 같은 대체 스위치를 만들어 두면, JS는 그대로인데 죽은 규칙만 남는다.
    """
    prev, block = _t(PREV), _s6c_css()
    assert "lb.style.display = 'flex'" in prev and "style.display !== 'flex'" in prev
    assert ".kgp-lightbox.show" not in block


def test_screens_render():
    """양쪽 화면이 실제로 200으로 뜬다(마크업 재구성 후 회귀 0)."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    assert c.get("/seller/collect/history").status_code == 200
    assert c.get("/seller/collect/history?q=zzz&status=archived").status_code == 200
