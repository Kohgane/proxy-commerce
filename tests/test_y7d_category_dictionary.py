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
    # 같은 길이 동점 → 적중 수: 「원예 전정」(6행 2개) vs 「문구」(8행 1개)
    assert SS.match_details("원예 전정 문구")["row"] == 6
    # 완전 동점 → 위 줄: 「가위」(6행) vs 「문구」(8행)
    assert SS.match_details("가위 문구")["row"] == 6


def test_no_hit_is_empty_and_default_leaf_only_in_resolve():
    assert SS.match_category("플리츠 미니멀 여성 여름 세트") == ""
    assert SS.resolve_category("플리츠 미니멀 여성 여름 세트") == SS.DEFAULT_LEAF_CATEGORY


# ── Y7-D 후속(오너 2026-10-08): 「노트」「허브」「데스크」 삭제 → 쿠팡 예측 다리로 ───────────────────────

BROAD = ["알루미늄 합금 휴대폰 및 노트북 스탠드 (자석 베이스 및 8단계 높이 조절) 아이패드 및 휴대폰에 적합",   # 운영 상품명
         "USB 허브 7포트 알루미늄",
         "LED 충전식 터치 크리에이티브 데스크 램프, 침실, 공부방, 거실 장식을 위한 조절 가능한 조명"]               # 운영 상품명


@pytest.mark.parametrize("title", BROAD)
def test_removed_words_no_longer_decide(title):
    assert SS.match_category(title) == ""


def test_removed_words_go_to_coupang_bridge(monkeypatch):
    """사전이 안 정하면 → 학습 → 쿠팡 예측 다리(Y7-C/E). 세 상품명 모두 출처가 「coupang」."""
    from src.uploaders import naver_categories as NC
    from src.db import image_translate_queue_pg as ST
    NC.reset()
    ST.state_set(NC.STATE_KEY, {})
    ST.state_set(NC.SUGGEST_KEY, {})
    monkeypatch.setattr(NC, "BACKGROUND", False)
    monkeypatch.setattr(NC, "_fetch", lambda account="": [
        {"id": "50000151", "name": "노트북", "wholeCategoryName": "디지털/가전>노트북액세서리>노트북거치대", "last": True},
        {"id": "50000152", "name": "USB허브", "wholeCategoryName": "디지털/가전>PC액세서리>USB허브", "last": True},
        {"id": "50000153", "name": "스탠드", "wholeCategoryName": "가구/인테리어>인테리어소품>스탠드", "last": True}])
    asked = []

    class Fake:
        access_key, secret_key = "ak", "sk"

        def predict(self, name, desc=""):
            asked.append(name)
            leaf = "노트북거치대" if "노트북" in name else ("USB허브" if "허브" in name else "스탠드")
            return {"id": "9", "name": leaf, "type": "SUCCESS", "why": ""}
    import src.channel_sync.coupang_uploader as CU
    monkeypatch.setattr(CU, "make_uploader", lambda: (Fake(), ""))
    try:
        for t in BROAD:
            cid, src = NC.pick({"title_ko": t, "cat_scope": "s:y7d-broad"})
            assert src == "coupang", (t, cid, src)
        assert len(asked) == 3
    finally:
        NC.reset()
        ST.state_set(NC.STATE_KEY, {})
        ST.state_set(NC.SUGGEST_KEY, {})


def test_dictionary_words_left():
    """남은 사전 낱말 — 보고서와 같은 목록(추가는 리프 ID·테스트와 함께만)."""
    words = [t for p, _ in SS.CATEGORY_PATTERNS for t in p.split("|")]
    assert "노트" not in words and "허브" not in words and "데스크" not in words
    assert len(words) == 59
