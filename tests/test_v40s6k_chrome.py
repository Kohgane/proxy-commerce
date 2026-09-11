"""tests/test_v40s6k_chrome.py — 6-k: 전역 chrome + 토큰 단일 소스.

세 가지를 지킨다.

**① 정의되지 않은 토큰을 폴백 없이 쓰지 않는다.**
   CSS 커스텀 속성은 정의가 없으면 **조용히 속성을 죽인다** — 배경이 투명해지고 색이 기본값이 된다.
   에러도 경고도 없다. 실측(2026-09-11): 6곳이 그렇게 죽어 있었다
   (`.kgp-badge-quiet`·`.ch-badge-src` 배경, `.pc-code-chip` 배경, `--ink-soft` 색 2곳).
   **그중 하나는 내가 #714에 넣은 것이다** — 스킬 문서에 있는 이름(`--hanji`)을 쓰면 당연히
   정의돼 있을 줄 알았다. 그 가정을 이 계약이 대신 검사한다.

**② 전역 chrome은 인라인이 아니라 CSS에 산다.**
   `_base.html`은 전 화면에 걸린다. 인라인으로 두면 화면마다 다르게 흘러가고,
   실제로 `.console-account`는 **클래스만 있고 규칙이 없어** 인라인이 그 자리를 대신하고 있었다.

**③ 색은 토큰에서 파생한다.** `pc-status` 4규칙이 raw hex였다 —
   "app.css 토큰 단일 소스, 하드코딩 hex 금지"라는 **규칙 위반이 규칙의 집 안에** 있었다.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path("src/static/app.css")
CONSOLE = Path("src/seller_console/static/console.css")
SELLER = Path("src/seller_console/static/seller.css")
BASE = Path("src/seller_console/templates/_base.html")
CSS_FILES = (APP, CONSOLE, SELLER)

# hex는 뒤에 hex 아닌 문자가 와야 한다 — 안 그러면 `#fbBtn` 같은 **ID 선택자**를 색으로 읽는다
#   (이 스위트에서 실제로 그렇게 헛짚었다).
HEX = r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?![0-9a-zA-Z_-])"


def _decl(p: Path) -> str:
    """주석 제거 — 주석 속 hex는 설명이지 선언이 아니다(내 설명문이 내 계약을 깨면 안 된다)."""
    return re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)


# ── ① 미정의 토큰 ────────────────────────────────────────────────────────────
def test_no_custom_property_is_used_without_being_defined():
    """★ 정의 없는 `var(--x)`는 **에러가 아니라 침묵**이다 — 그 속성만 사라진다.

    선언이 한 줄에 여러 개 있을 수 있어(`--bg: …; --surface: …;`) 줄 앵커로 세면 안 된다.
    이 스위트에서 그렇게 세다가 "203곳 미정의"라는 거짓 경보를 낼 뻔했다.
    """
    css = "".join(_decl(p) for p in CSS_FILES)
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    used_bare = set(re.findall(r"var\((--[a-z0-9-]+)\s*\)", css))   # 폴백 **없는** 것만
    missing = sorted(used_bare - defined)
    assert not missing, f"폴백 없이 쓰는데 정의가 없다(속성이 죽는다): {missing}"


def test_design_skill_token_names_resolve():
    """★ 스킬 문서에 적힌 이름은 **실제로 있어야** 한다 — 문서대로 썼는데 안 먹으면 그게 함정이다."""
    css = "".join(_decl(p) for p in CSS_FILES)
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    for tok in ("--hanji", "--ink-soft", "--gold", "--teal", "--orange", "--ink"):
        assert tok in defined, f"스킬 정본 토큰 미정의: {tok}"


# ── ② 전역 chrome ────────────────────────────────────────────────────────────
def test_base_chrome_has_no_hardcoded_inline_style():
    """★ `_base.html`은 전 화면에 걸린다 — 인라인 하드코딩이 여기 있으면 전 화면이 물든다."""
    s = re.sub(r"\{#.*?#\}|<!--.*?-->", "", BASE.read_text(encoding="utf-8"), flags=re.S)
    bad = [x for x in re.findall(r'style="([^"]*)"', s)
           if re.search(HEX + r"|rgba?\(|\d+px", x)]
    assert not bad, f"_base 인라인 하드코딩 잔존: {bad[:2]}"


def test_base_chrome_uses_our_button_grammar():
    """★ 전역 chrome의 보조 버튼은 전부 고스트 — v2 아웃라인/컬러 유틸 0."""
    s = BASE.read_text(encoding="utf-8")
    assert "btn-outline-" not in s, "전역 chrome에 v2 아웃라인 버튼이 남았다"
    assert "text-bg-" not in s, "전역 chrome에 v2 컬러 뱃지가 남았다"


def test_console_account_has_a_rule_not_just_a_name():
    """★ `.console-account`는 **이름만 있고 규칙이 없었다** — 인라인이 그 자리를 대신했다.

    이름이 있는데 집이 없으면, 다음 사람은 그 이름을 믿고 쓰다가 아무 일도 안 일어나는 걸 본다.
    """
    css = _decl(CONSOLE)
    for cls in (".console-account", ".console-avatar", ".fb-wrap", ".fb-btn"):
        assert re.search(re.escape(cls) + r"\s*\{", css), f"클래스 규칙 없음: {cls}"


# ── ③ 색은 토큰에서 ──────────────────────────────────────────────────────────
def test_pc_status_derives_from_tokens():
    """★ 규칙의 집 안에 있던 규칙 위반 — `pc-status` 4규칙이 raw hex였다.

    이동폭 실측(RGB 합차): success 13 · info 13 · warning 12 · danger 8 — **네 변형 다 거의 같다.**
    `info`만 색조가 파랑 → 청록으로 바뀌는데, 파랑은 애초에 우리 팔레트에 없던 색이라
    그건 변경이 아니라 **수정**이다.
    """
    css = _decl(APP)
    block = "".join(re.findall(r"\.pc-status-[a-z]+\s*\{[^}]*\}", css))
    assert block, "pc-status 변형 규칙을 못 찾았다"
    assert not re.search(HEX, block), f"pc-status에 raw hex 잔존: {re.findall(HEX, block)}"
    assert block.count("color-mix") >= 8, "토큰 파생이 아니다(배경·보더 8개)"


def test_console_and_seller_css_have_no_foreign_palette():
    """★ 우리 팔레트 밖 색이 들어와 있었다 — 부트스트랩 파랑·회색이 대표적이다."""
    for p in (CONSOLE, SELLER):
        body = _decl(p)
        foreign = [h for h in re.findall(HEX, body)
                   if h.lower() in ("#0d6efd", "#6c757d", "#0dcaf0", "#198754", "#dc3545")]
        assert not foreign, f"{p.name}에 부트스트랩 팔레트 잔존: {foreign}"
