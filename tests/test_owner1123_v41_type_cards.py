"""오너 10-28 절 1·2 마무리(11-23 C PR3) — 글자 14px·캡션 13px 토큰 · 대시보드 「마켓별 현황」 계정 카드.

- `--small: 14px` · `--caption: 13px`(오너 원칙: 최소 14px, 캡션 13px).
- 대시보드 작은 글자(op-tile-sub · od-stat-k · hb-tile-k · hb-rtitle · 사이드바 그룹 제목)는 rem 숫자 대신 `var(--caption)`.
- 마켓별 현황은 표가 아니라 카드(`.hb-mcards`) — 각 칸 링크(`hb-mcell`)는 그대로 목록 필터로 간다.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path("src/static/app.css").read_text(encoding="utf-8")
CON = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
DASH = Path("src/seller_console/templates/dashboard.html").read_text(encoding="utf-8")


def _rule(css: str, sel: str) -> str:
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", css)
    assert m, sel
    return m.group(1)


def test_type_tokens_are_14_and_13():
    assert re.search(r"--small:\s*14px", APP) and re.search(r"--caption:\s*13px", APP)


def test_dashboard_small_text_uses_caption_token():
    for sel in (".op-tile-sub", ".od-stat-k", ".hb-tile-k", ".hb-rtitle"):
        assert "font-size: var(--caption)" in _rule(APP, sel), sel
    assert "font-size: var(--caption)" in _rule(CON, ".console-nav-group-title")


def test_market_status_is_cards_not_table():
    i = DASH.index('class="hb-mcards"')
    block = DASH[i:i + 2500]
    assert 'data-role="hb-market-row"' in block and 'data-role="hb-mcell"' in block
    assert "<table" not in block
    assert "/seller/collect/history?mk={{ r.slot|urlencode }}&amp;mst=sale" in block      # 칸 → 목록 필터 그대로


def test_market_cards_use_tokens_only():
    seg = CON[CON.index(".hb-mcards {"):]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", seg)                                # 하드코딩 색 0
    for sel in (".hb-mcard .hb-mkt", ".hb-mcard-k", ".hb-mcard-sub", ".hb-mcard .hb-mtime"):
        assert "font-size: var(--caption)" in _rule(CON, sel), sel
    assert "font-size: var(--small)" in _rule(CON, ".hb-mcard .hb-mname")


def test_same_type_small_text_on_dashboard_and_footer():
    """같은 유형(실측 남은 12.8px 줄): 대시보드 「이미지 번역 n/한도」 꼬리 · 사업자 정보 바닥글 — 캡션 토큰."""
    assert "font-size: var(--caption)" in _rule(APP, ".hb-tile-v small")
    foot = Path("src/public_site/templates/public/_site_footer.html").read_text(encoding="utf-8")
    assert ".site-foot { font-size: var(--caption, 13px);" in foot


def test_tabbar_labels_are_caption_size():
    """같은 유형(390 실측): 하단 탭바 글자 11.8px → 캡션 13px."""
    css = Path("src/static/m_shell.css").read_text(encoding="utf-8")
    i = css.index(".kgp-mtab-item {")
    assert "font-size: var(--caption);" in css[i:css.index("}", i)]
