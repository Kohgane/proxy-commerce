"""tests/test_table_alignment_grammar.py — 표 정렬 문법 (오너 계약 6-e-2).

**표 정렬은 화면이 아니라 문법이다.** 화면마다 고치면 화면마다 다시 어긋난다.
`.pc-swiss-table`을 쓰는 표 전부에 같은 잣대를 댄다 — 새 표가 생겨도 자동으로 걸린다.

원칙(오너 E2):
  숫자·금액·날짜 = 우정렬 + 자릿수 맞춤(tabular-nums)
  텍스트 = 좌정렬 + 1줄 말줄임
  수직 정렬 통일 · 헤더 정렬 = 셀 정렬
  열 폭은 데이터가 흔들지 못하게

실측(1920×940)이 잡은 것 — **그리고 내 첫 진단이 틀렸던 것:**
진범은 orders 액션 열 하나다. 버튼 5개가 두 줄로 접혀 행이 99px가 되고, 첫 버튼 라벨
길이가 행마다 달라 뒤 버튼이 82px 밀렸다. 헤더/셀 정렬 불일치는 0, vertical-align은
전부 middle, 행 높이 종류도 1개였다 — **오너 용의자 ①②는 무죄.**
금액 열 시작 x가 8~10px 갈리는 건 **자릿수 차이의 정상 결과**다(우정렬이니 끝이 맞는다).
처음 그걸 원인으로 센 건 오독이고, `tabular-nums`는 원인 수리가 아니라 **보험**으로 남긴다.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates")
CSS = Path("src/static/app.css")

# `.pc-swiss-table`을 쓰는 표 전부 — 목록을 손으로 적지 않는다(새 표가 빠지지 않게).
TABLES = sorted(p for p in TPL.glob("*.html") if "pc-swiss-table" in p.read_text(encoding="utf-8"))

_NUMERIC_HEAD = re.compile(r"금액|가격|수량|건수|합계|총|재고|매출")


def _grammar_css() -> str:
    """표 정렬 문법 선언부만(주석은 옛 값을 근거로 인용하므로 제외)."""
    block = CSS.read_text(encoding="utf-8").split("표 정렬 문법")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def _heads(html: str) -> list[tuple[str, str]]:
    """(th 속성, 헤더 텍스트) — thead 안의 것만."""
    thead = re.search(r"<thead.*?</thead>", html, re.S)
    if not thead:
        return []
    # `<th` 는 `<thead` 도 잡는다 — 단어 경계를 준다(내 첫 판에서 실제로 난 오탐).
    return [(a, re.sub(r"<[^>]+>", "", t).strip())
            for a, t in re.findall(r"<th\b([^>]*)>(.*?)</th>", thead.group(0), re.S)]


def test_every_table_shares_one_source():
    """표가 여섯이다 — 규칙은 한 곳에만 둔다(화면마다 두면 화면마다 어긋난다)."""
    assert len(TABLES) >= 5, f"pc-swiss-table 표를 못 찾았다: {TABLES}"
    names = {p.name for p in TABLES}
    for must in ("orders.html", "collect_history.html", "markets.html"):
        assert must in names, f"{must}이 공통 표 문법 밖에 있다"


def test_tabular_nums_is_declared_once_for_all_tables():
    """자릿수 맞춤은 **보험**이다 — 원인 수리가 아니다(첫 진단을 실측이 반증했다).

    비례 숫자 폰트에서 숫자 열을 세로로 훑을 때 자릿수가 어긋나는 걸 막는다.
    표 하나가 아니라 **표 문법**에 걸어야 다음 표도 자동으로 산다.
    """
    css = _grammar_css()
    assert "font-variant-numeric: tabular-nums" in css
    # 화면별 슬라이스에 중복 선언하지 않는다(단일 소스).
    whole = CSS.read_text(encoding="utf-8")
    assert whole.count("font-variant-numeric: tabular-nums") <= 3, "자릿수 규칙이 여러 곳에 흩어졌다"


def test_header_alignment_matches_cell_alignment():
    """헤더 정렬 = 셀 정렬. 숫자 헤더가 좌정렬이고 셀만 우정렬이면 열이 어긋나 보인다."""
    for p in TABLES:
        html = p.read_text(encoding="utf-8")
        for attrs, text in _heads(html):
            if _NUMERIC_HEAD.search(text):
                assert "text-end" in attrs or "text-center" in attrs, \
                    f"{p.name}: 숫자 헤더 '{text}'가 좌정렬 — 셀은 우정렬이라 어긋난다"


def test_text_cells_get_one_line_ellipsis():
    """텍스트 열은 1줄 말줄임 — 긴 값이 줄을 늘려 행 높이를 흔들지 못하게."""
    css = _grammar_css()
    block = css.split("td.cardcell-title")[1].split("}")[0]
    for need in ("text-overflow: ellipsis", "white-space: nowrap", "overflow: hidden"):
        assert need in block, need


def test_ellipsis_does_not_eat_multi_block_cells():
    """★ 말줄임이 **잘라선 안 되는 값**을 잘라먹지 않게 예외를 둔다.

    셀 안에 블록(뱃지 줄·부가 설명)이 있으면 nowrap이 뒷줄을 통째로 숨긴다.
    잘림보다 어긋남이 낫다는 뜻이 아니라, 그 값은 잘리면 안 된다는 뜻이다.
    """
    css = _grammar_css()
    assert ":has(> div)" in css and "white-space: normal" in css


def test_action_column_lines_up_inside_itself():
    """★ 진범. 열은 섰는데 열 **안**이 안 섰다 — 첫 버튼 라벨 길이가 행마다 달라 뒤가 82px 밀렸다.

    ★ 그리고 `text-align`만으론 **아무 일도 안 난다**: 자식이 `d-flex`라 flex 컨테이너가
      text-align을 무시한다. 계산값엔 `right`가 찍히는데 렌더는 그대로였다(실측 확인).
      배치를 정하는 건 `justify-content`다 — 그래서 둘 다 건다.
    """
    css = _grammar_css()
    block = css.split("td.cardcell-actions {")[1].split("}")[0]
    assert "text-align: right" in block
    assert "td.cardcell-actions > .d-flex { justify-content: flex-end; }" in css, \
        "flex 래퍼에 justify-content가 없다 — text-align만으론 안 먹는다"


def test_mobile_cards_opt_out_of_column_rules():
    """모바일 카드에선 값이 제 줄을 갖는다 — 열 규칙은 표일 때만 산다."""
    css = _grammar_css()
    mobile = css.split("@media (max-width: 767.98px)")[1]
    assert "white-space: normal" in mobile and "max-width: none" in mobile
    assert "text-align: left" in mobile          # 액션 우정렬 해제
    assert "justify-content: flex-start" in mobile


def test_vertical_align_is_uniform():
    """수직 정렬 통일 — 뱃지 든 셀과 텍스트 셀이 행 안에서 따로 놀지 않게."""
    console = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
    td = console.split(".pc-swiss-table > tbody > tr > td {")[1].split("}")[0]
    assert "vertical-align: middle" in td
    # 화면 슬라이스가 이걸 뒤집지 않는다.
    whole = CSS.read_text(encoding="utf-8")
    assert "vertical-align: top" not in whole.split("표 정렬 문법")[1]


def test_no_per_screen_table_alignment_overrides():
    """★ 화면 슬라이스가 표 정렬을 따로 정하면 문법이 깨진다 — 규칙은 한 곳뿐이다."""
    whole = CSS.read_text(encoding="utf-8")
    before = whole.split("표 정렬 문법")[0]
    before = re.sub(r"/\*.*?\*/", "", before, flags=re.S)
    for slice_name in ("Stage 6-c", "Stage 6-d", "Stage 6-e"):
        if slice_name not in before:
            continue
        block = before.split(slice_name)[1]
        assert "tabular-nums" not in block, f"{slice_name}에 자릿수 규칙 중복"
        assert "text-overflow: ellipsis" not in block or "od-" in block, \
            f"{slice_name}이 표 말줄임을 따로 정한다"


# ── 렌더 실측: 규칙이 실제로 먹는지 ──────────────────────────────────────────
def test_screens_still_render():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    for path in ("/seller/orders", "/seller/collect/history", "/seller/markets",
                 "/seller/catalog", "/seller/settlement"):
        assert c.get(path).status_code == 200, path
