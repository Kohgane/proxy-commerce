"""tests/test_v40s6g_catalog.py — 디자인 v3 Stage 6-g: 내 상품(카탈로그).

오너 확산 순서에서 **건너뛰고 지나간 화면**이다(3번인데 6-e·6-f를 먼저 했다). 여기서 닫는다.

이 화면의 본론은 카드 문법 승계보다 **중복 정리**였다:
  · 같은 조건(`total == 0`)에 빈 상태가 **둘** 렌더됐다 — 같은 말을 두 번 하면 둘 다 안 읽힌다.
  · 6-f에서 은퇴시킨 부트스트랩 컬러 토스트(`text-bg-*`)가 여기 남아 있었다.
  · v2 래퍼 `.pc-action-table`(하드코딩 `#f8f8ff` 호버)을 달고 있었다.

로직 변경 0. 무한스크롤·나이아 레일·동기화 버튼이 잡는 훅 이름은 **그대로**다 —
훅을 건드리면 그건 디자인 작업이 아니라 기능 변경이다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/catalog.html")
ROWS = Path("src/seller_console/templates/catalog_rows.html")
CSS = Path("src/static/app.css")


def _body(p: Path) -> str:
    """주석·스크립트를 걷어낸 화면 몫만 — 근거를 적은 문장이 잔재로 잡히지 않게."""
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    return re.sub(r"\{#.*?#\}|<!--.*?-->", "", s, flags=re.S)


@pytest.fixture(scope="module")
def html():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    r = app.test_client().get("/seller/catalog")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ── 문법 승계 ────────────────────────────────────────────────────────────────
def test_op_card_grammar():
    """카드 1장에 헤더/바디/푸터 — 6-a~6-f와 같은 문법."""
    b = _body(TPL)
    assert 'class="ct-page"' in b
    for hook in ("op-card", "op-card-head", "op-card-body", "op-card-foot"):
        assert hook in b, hook
    assert "console-card" not in b, "v2 카드가 남았다"


def test_v2_wrapper_is_gone():
    """★ `.pc-action-table`(v2 래퍼) 철거. 그 규칙의 하드코딩 hex도 토큰으로 바꿨다.

    orders는 아직 이 클래스를 달고 있다(채점 끝난 화면) → 6-j 부채. 그래서 **규칙 자체**를
    고쳐 두 화면이 같이 이득을 본다. 마크업이 아니라 선언을 고치는 쪽이 옳을 때가 있다.
    """
    assert "pc-action-table" not in _body(TPL)
    css = CSS.read_text(encoding="utf-8")
    rule = css.split(".pc-action-table .table tbody tr:hover")[1].split("}")[0]
    assert "#" not in rule, f"하드코딩 hex 잔존: {rule.strip()}"
    assert "var(--" in rule


def test_no_bootstrap_color_utilities():
    """부트스트랩 색 유틸은 **상태 의미색만** 남긴다(6-f 규율 승계)."""
    b = _body(TPL) + _body(ROWS)
    banned = re.findall(r"\b(?:text-bg-\w+|btn-outline-\w+|alert-(?:warning|danger|info|success)|bg-white)\b", b)
    assert not banned, f"부트스트랩 색 유틸 잔존: {sorted(set(banned))}"


def test_inline_hardcoding_is_only_the_shared_chrome(html):
    """이 화면 몫 인라인 하드코딩 0. 남는 2건은 `_base.html` 공통 chrome(6-j)."""
    b = _body(TPL) + _body(ROWS)
    inline = re.findall(r'\sstyle="[^"]{4,}"', b)
    # min-height:1px 한 줄만 남긴다 — IntersectionObserver 관측 대상이 높이 0이면 안 잡힌다.
    assert [x for x in inline if "min-height:1px" not in x] == [], f"인라인 잔존: {inline}"


# ── 중복 정리 (이 슬라이스의 본론) ───────────────────────────────────────────
def test_empty_state_is_declared_once(html):
    """★ 같은 조건에 빈 상태 **하나**. 둘이면 둘 다 안 읽힌다."""
    assert html.count("아직 등록된 상품이 없어요") == 1
    assert "아직 수집된 상품이 없어요" not in html, "합치기 전 문장이 남았다"
    # 없앤 게 아니라 합친 것 — 다음 행동은 그대로 있어야 한다.
    assert "/seller/collect" in html and "/seller/listing/ai-create" in html


def test_empty_screen_shows_no_empty_table(html):
    """★ 0건이면 표를 감춘다 — 값 없는 열 제목만 남기는 건 정보가 아니라 자리 낭비다.

    감추되 **지우지는 않는다**: 무한스크롤·나이아 레일이 `#catalogRows`를 잡는다(훅 보존).
    """
    b = _body(TPL)
    assert '{% if total == 0 and not error_msg %} d-none{% endif %}' in b
    assert 'id="catalogRows"' in b                      # 훅은 DOM에 그대로 있다
    # 이동할 게 없으면 이동 안내도 없다.
    assert b.index("{% if total %}\n      <div class=\"ct-railnote\"") > 0


def test_one_filled_button_per_screen(html):
    """★ 강조 1색·주 행동 1개. 비어 있을 때 헤더 CTA를 내리는 이유는 **같은 곳으로 가는**
    채운 버튼이 둘이 되기 때문이다(헤더 '새 상품 수집' = 빈 상태 '수집기 열기' = /seller/collect).
    """
    b = _body(TPL)
    head = b.split("ch-head")[1].split("</div>\n  </div>")[0]
    assert "{% if total %}" in head, "0건에서도 헤더 CTA가 뜬다"
    # 필터 제출은 고스트(6-e 승계) — 6-c는 아직 채움이다(6-j 부채).
    assert '<button type="submit" class="btn btn-ghost btn-sm">검색</button>' in b
    assert b.count("btn-primary") == 2                  # 헤더 CTA 1 + 빈 상태 CTA 1(동시에 안 뜬다)


def test_mobile_card_label_does_not_split_a_word():
    """★ 라벨 폭 고정이 '마지막 동기화'를 두 줄로 잘랐다 — 세로쪼개짐은 금지다.

    카드 표 셋(카탈로그·주문·수집이력)이 같은 규칙을 쓰니 **한 곳만 고치면 셋 다** 낫는다.
    """
    css = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
    rule = css.split("td[data-label]::before {")[1].split("}")[0]
    assert "white-space: nowrap" in rule
    assert "flex: 0 0 60px" not in rule, "폭을 다시 고정하면 같은 자리에서 또 쪼개진다"
    assert "min-width: 60px" in rule                    # 최소 폭은 유지(열이 흔들리지 않게)


def test_touch_targets_on_mobile():
    """★ 제목 줄 주 행동 버튼이 36px였다 — 손가락으로 누르는 자리다.

    `.ch-head`는 6-c·6-e·6-g가 같이 쓰니 **모바일에서만** 키웠다. 데스크톱 채점이 끝난
    두 화면의 렌더는 건드리지 않고, 터치에서만 규칙(≥44px)을 지킨다.
    """
    css = CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 767.98px) { .ch-head .btn { min-height: 44px; } }" in css


def test_old_bootstrap_toast_is_retired():
    """★ 6-f에서 은퇴시킨 패턴이 여기 남아 있었다 — 같은 유형은 같이 잡는다."""
    s = TPL.read_text(encoding="utf-8")
    js_raw = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", s, re.S))
    # 주석은 걷어내고 본다 — 무엇을 없앴는지 적어 둔 문장이 잔재로 잡히면
    # **설명을 지워야 통과하는 계약**이 된다(이 세션에서 네 번째로 만나는 오탐).
    js = re.sub(r"^\s*//.*$", "", re.sub(r"/\*.*?\*/", "", js_raw, flags=re.S), flags=re.M)
    code = _body(TPL) + js
    assert "catalogToast" not in code and "bootstrap.Toast" not in code
    assert "text-bg-" not in code
    assert "window.pcToast" in js
    # 조용히 삼키지 않는다 — pcToast가 없으면 콘솔에 남긴다(6-f와 같은 규율).
    assert "console.log" in js.split("function showCatalogToast")[1][:300]


def test_no_fourth_duplicate_component():
    """★ 넷째를 만들지 않는다 — 필터 줄·행 액션은 **이름만 공용으로 승격**했다.

    6-e가 이미 같은 선언을 갖고 있었다. 새로 `.ct-filter`를 만들면 숫자 타일 3중복과
    똑같은 부채가 하나 더 생긴다(그 주석이 브레이크다).
    """
    css = CSS.read_text(encoding="utf-8")
    # 6-j: 승격을 **개명으로 완결**했다. 6-g에선 `.od-filter, .op-filter`로 이름 둘을 남겼는데,
    #   이름이 둘이면 다음 화면이 어느 쪽을 쓸지 고르게 되고 그게 세 번째 이름의 시작이다.
    #   이 계약의 의도("넷째를 만들지 않는다")는 그대로 — 검사 대상만 최종형으로 옮긴다.
    assert ".od-filter" not in css, "옛 이름이 남았다(개명 미완)"
    assert ".op-filter {" in css, "공용 필터 선언이 사라졌다"
    assert ".ct-filter" not in css, "같은 일을 하는 넷째 컴포넌트를 만들었다"
    assert 'class="op-filter' in _body(TPL)
    # 선언은 6-e 것 그대로 — 승격·개명은 이름만이다.
    block = css.split(".op-filter {")[1].split("}")[0]
    assert "display: flex" in block and "flex-wrap: wrap" in block


# ── 로직 변경 0 (훅 계약) ────────────────────────────────────────────────────
HOOKS = (
    'id="catalogFilters"', "kgp-filter-toggle", 'id="catalogRows"', "data-fs-list", "data-fs-root",
    'id="fsInfiniteScroll"', 'id="fsLoadingSpin"', 'id="fsAllLoaded"', "data-loaded=", "data-total=",
    "data-has-more=", "data-per-page=", "KGPFastScroll", "kgp-fastscroll.js", "syncItem(",
    "showCatalogToast", "setButtonLoading", "/seller/catalog/count", "kgpCatNewBanner",
    "__kgpTeardown", "fmt=rows", "catalog_rows.html",
)


@pytest.mark.parametrize("hook", HOOKS)
def test_hooks_survive(hook):
    """JS가 잡는 자리는 이름 하나도 안 바꾼다."""
    assert hook in TPL.read_text(encoding="utf-8"), hook


def test_row_hooks_survive():
    s = ROWS.read_text(encoding="utf-8")
    for hook in ("data-fs-key", "cardcell-img", "cardcell-title", "cardcell-actions",
                 "onclick=\"syncItem(", "data-label="):
        assert hook in s, hook


def test_sync_button_states_are_honest():
    """미연동 마켓은 **눌러도 안 되는 자리**라고 화면이 말한다(죽은 버튼 0)."""
    s = ROWS.read_text(encoding="utf-8")
    assert "disabled aria-disabled=\"true\"" in s and "연동 필요" in s


# ── 표 문법 (6-e-2 공통 계약과 같은 잣대) ────────────────────────────────────
def test_table_keeps_swiss_grammar(html):
    assert "pc-swiss-table" in html and "table-cards" in html
    assert "table-light" not in _body(TPL), "6-c·6-d는 thead 유틸을 안 쓴다"
    # 가격은 숫자 열 — 헤더·셀 둘 다 우정렬(정렬 문법 계약과 같은 규칙).
    assert '<th class="text-end">가격</th>' in _body(TPL)
    assert '<td class="text-end" data-label="가격">' in _body(ROWS)
    # 액션 열도 헤더·셀 정렬이 같아야 한다.
    assert '<th class="ct-col-act text-end">액션</th>' in _body(TPL)
    assert 'class="cardcell-actions text-end"' in _body(ROWS)


def test_screen_renders_with_and_without_data(html):
    """실데이터 유무와 무관하게 200 — 빈 상태도 화면이다."""
    assert "상품 카탈로그" in html and "내 상품" in html
