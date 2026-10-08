"""Y7-D(오너 2026-10-08) — 상품명 사전 매칭: 줄 순서 의존 제거 · 한 글자 낱말은 낱말 끝일 때만.

증거: 「여성 여름 반팔 티셔츠」 → 7행 「티」가 먼저 걸려 주방(50004737). 운영 수집 상품명 49건을 돌려 보니
바뀐 16건이 **전부 한 글자 「티」** — 「빈티지」「멀티탭」「크리에이티브」「스티커」「물티슈」 안의 「티」가 주방으로 갔다.
"""
from __future__ import annotations

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

CLOTHES, KITCHEN, STATIONERY = "50000167", "50004737", "50002335"


def test_tshirt_is_clothes_not_kitchen():
    d = SS.match_details("여성 여름 반팔 티셔츠")
    assert d["leaf"] == CLOTHES and d["token"] == "티셔츠"


@pytest.mark.parametrize("title", [
    "빈티지 티테이블 겸 TV장, 거실용",                                       # 운영 상품명 — 빈티지·티테이블
    "JOYE 책상 상판 이중 트랙 패널 멀티탭 고속충전 스테이션",                    # 멀티탭
    "자체 접착식 케이블 라벨 프린터 스티커 정리 도구",                          # 스티커
    "욕실 화장지 케이스, 물티슈, 휴지 서랍 수납 선반",                          # 물티슈
    "보이차 티백",                                                            # 티백 — 「티」는 앞 글자(중심 말은 「백」)
])
def test_single_char_inside_word_does_not_hit_kitchen(title):
    assert SS.match_category(title) != KITCHEN


@pytest.mark.parametrize("title,leaf", [
    ("밀크티 파우더", KITCHEN), ("아이스 티", KITCHEN),                      # 낱말 끝·낱말 전체
    ("크리스탈 와인잔 세트", KITCHEN),
])
def test_single_char_at_word_end_hits(title, leaf):
    assert SS.match_category(title) == leaf


def test_single_char_rule_boundary_mechanism():
    """「차」 같은 한 글자 규칙이 있다면: 「보이차」(끝 글자)는 맞음, 「차량용」(앞 글자)은 아님."""
    hit = SS._token_hit
    words = lambda t: [w for w in SS._WORD_SPLIT.split(t) if w]
    assert hit("차", "보이차 티백", words("보이차 티백")) is True
    assert hit("차", "접이식 차량용 책상", words("접이식 차량용 책상")) is False
    assert hit("티", "보이차 티백", words("보이차 티백")) is False


def test_longest_token_wins_then_hit_count_then_upper_row():
    """가장 긴 낱말 → 그 줄 낱말이 상품명에 더 많이 든 쪽 → 위 줄."""
    assert SS.match_details("캔들 디퓨저")["hits"] == ["캔들", "디퓨저"]
    # 「주얼리」(3) 4행 vs 「키링」(2) 3행 — 예전엔 3행(위)이 먼저였지만 이제 더 긴 낱말
    assert SS.match_details("키링 주얼리")["row"] == 4
    # 같은 길이(2자) — 「스트랩」(3, 3행)과 「가방」(2, 2행): 긴 쪽
    assert SS.match_details("가방 스트랩")["token"] == "스트랩"
    # 같은 길이 동점 → 적중 수: 「원예 전정」(6행 2개) vs 「노트」(8행 1개)
    assert SS.match_details("원예 전정 노트")["row"] == 6
    # 완전 동점 → 위 줄: 「가위」(6행) vs 「노트」(8행)
    assert SS.match_details("가위 노트")["row"] == 6


def test_no_hit_is_empty_and_default_leaf_only_in_resolve():
    assert SS.match_category("플리츠 미니멀 여성 여름 세트") == ""
    assert SS.resolve_category("플리츠 미니멀 여성 여름 세트") == SS.DEFAULT_LEAF_CATEGORY
