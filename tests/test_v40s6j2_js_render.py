"""tests/test_v40s6j2_js_render.py — 6-j-2: JS가 그리는 마크업도 화면이다.

**화면이 그리는 것과 계약이 보는 것이 다르면, 그린은 그 차집합만큼 거짓이다.**

실증(2026-09-10): 6-i 계약 `test_bootstrap_color_utilities_are_gone`은 `_body()`로 읽는데
그 헬퍼가 `<script>`를 지웠다 → 계약 `1 passed`, 같은 파일 JS 안에는 위반 **7종 12건**.
"v2 잔재 0"으로 머지된 화면이 지금도 v2 마크업을 그리고 있었다.

지울 것과 안 지울 것의 기준은 '노이즈인가'가 아니라 **'사용자가 보게 되는가'**다 —
주석은 화면에 안 나오지만 JS 문자열은 **화면이 된다**.

이 계약은 **템플릿 8~9개의 슬라이스 계약을 다 고치는 대신** 한 곳에서 전 템플릿의
`<script>` 영역을 본다. 슬라이스가 늘어도 여기 한 줄이 계속 지킨다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TPL_DIR = Path("src/seller_console/templates")

# 화면에 나가면 안 되는 v2 문법. 서버 렌더에 걸던 것과 **같은 규칙**을 JS에도 건다
#   (규칙이 영역마다 다르면 그 경계가 곧 다음 사각이다).
V2_PATTERNS = {
    "text-bg-*": r"text-bg-[a-z]+",
    "badge bg-*": r"badge bg-[a-z-]+",
    "btn-outline-*": r"btn-outline-[a-z]+",
    "alert alert-*": r"alert alert-[a-z]+",
    "bg-{color}": r"\bbg-(?:primary|secondary|success|info|warning|danger|light|dark)\b",
    "v2 .card": r'class=\\?"[^"]*(?<![\w-])card(?![\w-])',
    "하드코딩 hex/px": r'style=\\?"[^"]*(?:#[0-9a-fA-F]{3,6}|\d+px)',
}


def _js(path: Path) -> str:
    """템플릿의 `<script>` 안쪽 — **화면이 되는 문자열**이 사는 곳."""
    return "\n".join(re.findall(r"<script[^>]*>(.*?)</script>",
                                path.read_text(encoding="utf-8"), re.S))


def _violations(text: str) -> dict:
    out = {}
    for name, pat in V2_PATTERNS.items():
        n = len(re.findall(pat, text))
        if n:
            out[name] = n
    return out


@pytest.mark.parametrize("tpl", sorted(TPL_DIR.glob("*.html")), ids=lambda p: p.name)
def test_js_render_strings_use_our_grammar(tpl):
    """★ JS가 만드는 마크업에도 우리 문법을 건다 — 서버 렌더와 **같은 규칙**으로.

    실측 착수 좌표(2026-09-10): 46건 · 11장.
      `btn-outline-*` 23 → `btn-ghost` · `text-bg-*` 11 → `pc-badge` 변형 ·
      `bg-{color}` 5 · 하드코딩 4 · `badge bg-*`·`alert alert-*`·v2 `.card` 각 1.
    """
    bad = _violations(_js(tpl))
    assert not bad, f"{tpl.name} JS 렌더 문자열에 v2 문법: {bad}"


def test_slice_contracts_do_not_blind_themselves_to_script():
    """★★ 이 사각을 **만든 습관**을 막는다 — 계약이 `<script>`를 지우고 검사하지 않는다.

    지우려면 그 안을 **따로 검사하는 짝**을 반드시 같이 둬야 한다. 짝 없이 지우면
    "계약 그린 + 화면 틀림"이 조용히 성립한다(6-i가 실제로 그랬다).

    전처리 헬퍼(`_body()`·`_slice_css()`)가 바로 그 경로다 — 계약을 쓸 때 한 번 묻는다:
    **"이 계약이 그린인데 화면이 틀릴 수 있는 경로가 있나?"**
    """
    strippers = []
    for t in sorted(Path("tests").glob("test_v40s6*.py")):
        src = t.read_text(encoding="utf-8")
        strips = re.search(r're\.sub\(\s*r?"<script.*?</script>"', src)
        if not strips:
            continue
        # 지우는 계약은 **JS를 따로 보는 짝**이 있어야 한다.
        has_pair = ("<script[^>]*>" in src) or ("_js(" in src)
        if not has_pair:
            strippers.append(t.name)
    assert not strippers, (
        f"`<script>`를 지우면서 JS를 따로 안 보는 계약: {strippers} — "
        "지우려면 짝을 두거나, 지우지 마라")


def test_the_shared_contract_actually_covers_every_template():
    """★ 이 계약이 **전 템플릿**을 도는지 못 박는다 — 한 장이라도 빠지면 그 장이 다음 사각이다."""
    seen = sorted(p.name for p in TPL_DIR.glob("*.html"))
    assert len(seen) >= 40, f"템플릿 수집이 이상하다({len(seen)}장) — 경로가 바뀌었나"
    # 파라미터화가 파일 목록에서 직접 오므로, 새 템플릿은 **자동으로** 이 계약에 편입된다.
    assert "sourcing.html" in seen and "collect_preview.html" in seen
