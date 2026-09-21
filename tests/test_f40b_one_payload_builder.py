"""F40-b 계약 — 등록 경로 **셋이 한 빌더를 지난다**.

## 왜 세 번째가 왔나 (카나리 4차 실측 2026-09-21)

같은 결함이 **두 번** 고쳐졌다:

| | 무엇을 고쳤나 | 무엇이 남았나 |
|---|---|---|
| F39 | `to_dict()`가 `url` 키를 안 만든다 | — |
| F40 | 행의 `url` 컬럼을 안 싣는다 | **일괄 경로만** 고쳐졌다 |
| **F40-b** | **단건(서랍)** 경로가 같은 문장을 냈다 | — |

라이브 원문: `상품 주소가 페이로드에 없습니다(빈 값) … 뽑힌 값: ''`

> ★★★ **두 번 같은 자리에서 빠졌으면 세 번째는 「경로가 늘어서」 온다.**
> 그래서 고치는 방식이 「그 경로도 고친다」가 아니라 **「경로를 열거하고 한 함수를 지나게 한다」**다.
> 오너 지시: *"F39/F40 계약을 세 경로 각각으로 늘려라 — 경로 열거 계약이 없으면 네 번째가 온다."*

## 단건 경로가 왜 빠졌나 — 삼키는 `try` 안에 있었다

주소 채우기가 **이미지·도달성 확인 `try` 블록 안**에 있었고, 그 `except`는 모든 예외를
삼키고 넘어간다. 앞쪽에서 무엇 하나 터지면 **주소 채우기가 조용히 건너뛰어진다.**
→ [[마켓 실패를 우리 성공으로 덮었다]]와 같은 계열(가리개가 사유를 먹는다).

라이브 호출 0.
"""
from __future__ import annotations

import inspect
import re

import pytest

from src.seller_console import views
from src.seller_console.upload_dispatcher import (DISPATCH_PATHS, build_dispatch_payload,
                                                  draft_url)

#: 페이로드를 만드는 **모든** 라우트/함수. 새 경로가 생기면 여기 올린다.
PAYLOAD_BUILDERS = (
    views.collect_upload,              # 단건(서랍)
    views.collect_bulk_upload,         # 일괄(수집 이력)
    views._woocommerce_dispatch,       # 재등록(멀티샵)
)

TMALL = "https://detail.tmall.com/item.htm?id=617129397971"


# ---------------------------------------------------------------------------
# 빌더 자체
# ---------------------------------------------------------------------------

def test_the_row_url_fills_an_empty_payload():
    """★★★ **F40-b의 판정 지점** — 행의 `url` 컬럼이 정본이다."""
    pd = build_dispatch_payload({"title": "수행방패"}, {"url": TMALL})
    assert draft_url(pd) == TMALL


def test_a_share_link_in_the_payload_is_still_replaced_by_a_usable_one():
    """★ 주소가 **있어도** 상품번호가 안 나오면 쓸 수 없다(F40) — 행 값이 이긴다."""
    from src.collectors.product_key import vendor_sku
    pd = build_dispatch_payload({"url": "https://e.tb.cn/h.abc?tk=XYZ"}, {"url": TMALL})
    assert vendor_sku(draft_url(pd))


def test_a_payload_that_already_works_is_left_alone():
    pd = build_dispatch_payload({"url": TMALL}, {"url": "https://other.example/x"})
    assert draft_url(pd) == TMALL


def test_no_row_means_no_invention():
    """★★ 행이 없으면 **지어내지 않는다** — 빈 채로 나가고 하류가 정직하게 멈춘다."""
    pd = build_dispatch_payload({"title": "t"}, None)
    assert draft_url(pd) == ""
    assert "url" not in pd


def test_the_builder_does_not_mutate_its_input():
    """★ 호출부의 dict을 바꾸면 **다른 경로가 영향을 받는다**(일괄은 루프 안이다)."""
    src = {"title": "t"}
    build_dispatch_payload(src, {"url": TMALL})
    assert "url" not in src


@pytest.mark.parametrize("row", [{}, {"url": ""}, {"url": "   "}, None])
def test_an_empty_row_url_changes_nothing(row):
    pd = build_dispatch_payload({"title": "t"}, row)
    assert "url" not in pd


# ---------------------------------------------------------------------------
# ★ 경로 열거 — 네 번째를 막는다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", PAYLOAD_BUILDERS, ids=lambda f: f.__name__)
def test_every_dispatch_path_goes_through_the_builder(fn):
    """★★★ **오너 지시의 판정 지점** — 세 경로가 각각 빌더를 부른다."""
    src = inspect.getsource(fn)
    assert "build_dispatch_payload" in src, f"{fn.__name__}이 빌더를 안 쓴다"


def test_the_path_list_matches_the_contract_population():
    """★ 경로 수가 늘면 **이 계약이 먼저 깨진다** — 그게 목적이다."""
    assert len(DISPATCH_PATHS) == len(PAYLOAD_BUILDERS)


def test_no_dispatch_call_bypasses_the_builder():
    """★★ `dispatch(...)`를 부르는 자리가 늘었는데 빌더를 안 지나면 잡는다.

    소스에서 `dispatcher.dispatch(` 호출을 세고, **그 함수들이 전부 위 목록**인지 본다.
    """
    src = (inspect.getsource(views))
    callers = set()
    cur = None
    for line in src.splitlines():
        m = re.match(r"\s*def (\w+)\(", line)
        if m:
            cur = m.group(1)
        if re.search(r"dispatcher\.dispatch\(", line) and cur:
            callers.add(cur)
    known = {f.__name__ for f in PAYLOAD_BUILDERS}
    assert callers <= known, f"빌더를 안 지나는 등록 경로가 생겼다: {callers - known}"


# ---------------------------------------------------------------------------
# 단건 경로 — 삼키는 블록 밖에 있다
# ---------------------------------------------------------------------------

def test_the_single_path_fills_the_url_outside_the_swallowing_try():
    """★★★ 이게 **F40-b의 근원**이다.

    주소 채우기가 이미지·도달성 `try` 안에 있으면, 그 블록이 **다른 이유로** 터졌을 때
    주소가 조용히 안 채워진다. 빌더 호출이 그 `try`보다 **앞**에 있어야 한다.
    """
    src = inspect.getsource(views.collect_upload)
    build_at = src.index("build_dispatch_payload")
    try_at = src.index("_warn_pages = []")       # 이미지·도달성 블록의 시작 표식
    assert build_at < try_at, "주소 채우기가 여전히 삼키는 블록 안이다"


def test_the_single_path_does_not_refill_inside_the_block():
    """★ 같은 일을 두 자리에서 하면 한쪽만 고쳐진다 — 블록 안의 옛 채우기는 사라졌다."""
    src = inspect.getsource(views.collect_upload)
    tail = src[src.index("_warn_pages = []"):]
    assert 'product_data["url"] =' not in tail


def test_the_fill_is_logged_so_the_next_canary_can_see_it():
    """★ F40이 남긴 규율 — 고른 주소를 로그에 남긴다(URL이라 마스킹 대상이 아니다)."""
    src = inspect.getsource(build_dispatch_payload)
    assert "logger.info" in src and "url=%s" in src
