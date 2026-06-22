"""tests/test_pro_design_v13.py — v13 프로 디자인 가드: 개발 표식 제거 + 지구본→글러브."""
from __future__ import annotations

import re
from pathlib import Path

USER_TEMPLATES = [
    "src/seller_console/templates/orders.html",
    "src/seller_console/templates/markets.html",
    "src/seller_console/templates/messaging.html",
    "src/templates/landing.html",
]

_PHASE_RE = re.compile(r"Phase\s+\d{2,}")


def _visible_text(html: str) -> str:
    # HTML 주석/Jinja 주석 제거 후 사용자 노출 텍스트만 검사
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"\{#.*?#\}", "", html, flags=re.DOTALL)
    return html


def test_no_visible_phase_markers_in_user_templates():
    for path in USER_TEMPLATES:
        text = _visible_text(Path(path).read_text(encoding="utf-8"))
        assert not _PHASE_RE.search(text), f"{path}에 개발 표식 'Phase NNN'이 노출됩니다"


def test_extension_uses_glove_not_globe():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "KGP_GLOVE_SVG" in cs
    assert "KGP_GLOBE_SVG" not in cs          # 지구본 변수 폐기
    # 오빗-글로브 잔재(회전 궤도 ellipse 2개) 없음
    assert "rotate(32 256 256)" not in cs and "rotate(-32 256 256)" not in cs


def test_favicon_and_icons_are_glove():
    svg = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    assert "글러브" in svg and "#020010" not in svg
