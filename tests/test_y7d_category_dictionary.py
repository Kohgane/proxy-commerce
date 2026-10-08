"""Y7-D(오너 2026-10-08) — 상품명 사전 매칭: 줄 순서 의존 제거 · 한 글자 낱말은 낱말 끝일 때만.

증거: 「여성 여름 반팔 티셔츠」 → 7행 「티」가 먼저 걸려 주방(50004737). 운영 수집 상품명 49건을 돌려 보니
바뀐 16건이 **전부 한 글자 「티」** — 「빈티지」「멀티탭」「크리에이티브」「스티커」「물티슈」 안의 「티」가 주방으로 갔다.
"""
from __future__ import annotations

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

CLOTHES, KITCHEN, STATIONERY = "50000167", "50004737", "50002335"

# Y7-D 결정 2(오너 2026-10-09)로 운영 사전은 「키링」 한 줄만 남았다. 아래 **매칭 장치**(가장 긴 낱말 → 적중 수 → 위 줄,
# 한 글자 낱말은 낱말 끝) 테스트는 예전 11줄을 **시험용 표**로 끼워 돌린다 — 장치는 그대로 살아 있어야 하므로.
_TEST_ROWS = (
    (r"피젯|EDC|스피너|슬라이더|엔진|오브제|퍼즐|모형|분재", '50004132'),
    (r"슬링백|백팩|가방|패킹큐브|파우치|토트", '50000646'),
    (r"키링|카라비너|스트랩", '50000570'),
    (r"목걸이|팔찌|체인|주얼리", '50000570'),
    (r"멀티툴|나이프|공구|드라이버|드릴|스크러버|에어펌프|레이저|인두", '50003413'),
    (r"가위|원예|전정", '50000406'),
    (r"잔|글라스|텀블러|머그|드리퍼|티|주전자|도마|주방", '50004737'),
    (r"만년필|문구|북마크", '50002335'),
    (r"신디사이저|이어팁|카드리더|오디오|스피커|헤드폰", '50000205'),
    (r"재킷|티셔츠|샌들|의류", '50000167'),
    (r"향|캔들|디퓨저", '50001854'),
)


@pytest.fixture
def rows(monkeypatch):
    monkeypatch.setattr(SS, "CATEGORY_PATTERNS", _TEST_ROWS)


def test_tshirt_is_clothes_not_kitchen(rows):
    d = SS.match_details("여성 여름 반팔 티셔츠")
    assert d["leaf"] == CLOTHES and d["token"] == "티셔츠"


@pytest.mark.parametrize("title", [
    "빈티지 티테이블 겸 TV장, 거실용",                                       # 운영 상품명 — 빈티지·티테이블
    "JOYE 책상 상판 이중 트랙 패널 멀티탭 고속충전 스테이션",                    # 멀티탭
    "자체 접착식 케이블 라벨 프린터 스티커 정리 도구",                          # 스티커
    "욕실 화장지 케이스, 물티슈, 휴지 서랍 수납 선반",                          # 물티슈
    "보이차 티백",                                                            # 티백 — 「티」는 앞 글자(중심 말은 「백」)
])
def test_single_char_inside_word_does_not_hit_kitchen(rows, title):
    assert SS.match_category(title) != KITCHEN


@pytest.mark.parametrize("title,leaf", [
    ("밀크티 파우더", KITCHEN), ("아이스 티", KITCHEN),                      # 낱말 끝·낱말 전체
    ("크리스탈 와인잔 세트", KITCHEN),
])
def test_single_char_at_word_end_hits(rows, title, leaf):
    assert SS.match_category(title) == leaf


def test_single_char_rule_boundary_mechanism():
    """「차」 같은 한 글자 규칙이 있다면: 「보이차」(끝 글자)는 맞음, 「차량용」(앞 글자)은 아님."""
    hit = SS._token_hit
    words = lambda t: [w for w in SS._WORD_SPLIT.split(t) if w]
    assert hit("차", "보이차 티백", words("보이차 티백")) is True
    assert hit("차", "접이식 차량용 책상", words("접이식 차량용 책상")) is False
    assert hit("티", "보이차 티백", words("보이차 티백")) is False


def test_longest_token_wins_then_hit_count_then_upper_row(rows):
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


def test_no_hit_is_empty_and_no_default_leaf():
    """Y7-D 결정 2: 기본 리프(50004132)는 운영 트리에서 「보드게임」 — 미적중을 거기로 보내지 않는다."""
    assert SS.match_category("플리츠 미니멀 여성 여름 세트") == ""
    assert SS.resolve_category("플리츠 미니멀 여성 여름 세트") == ""
    assert not hasattr(SS, "DEFAULT_LEAF_CATEGORY")


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


# ── Y7-D 결정 2(오너 2026-10-09): 운영 트리와 대조해 (a) 리프이고 (b) 경로 이름이 낱말 뜻과 맞는 것만 생존 ─────

#: 운영 네이버 트리(app_state `naver_categories`, 2026-10-08 23:37 KST)에서 확인한 리프 경로.
#: 사전에 낱말을 더하려면 **여기에 운영 트리 경로를 먼저 적고** 테스트를 붙인다.
VERIFIED_LEAVES = {"50000570": "패션잡화>패션소품>키링"}


def test_dictionary_words_left():
    """남은 사전 = 「키링」 하나(→ 패션소품>키링)."""
    words = [t for p, _ in SS.CATEGORY_PATTERNS for t in p.split("|")]
    assert words == ["키링"]


def test_every_dictionary_leaf_is_verified():
    """사전의 모든 리프 ID는 운영 트리에서 확인한 경로가 있어야 한다(짐작 ID 금지)."""
    for _p, leaf in SS.CATEGORY_PATTERNS:
        assert leaf in VERIFIED_LEAVES, leaf


@pytest.mark.parametrize("title", [
    # 운영 상품명(바뀐 34개 중) — 예전 판정: 의류 상위 분류·냉동고·멸치·숄더백·음향 상위 분류·키링
    "여름용 라운드넥 반팔 배색 자수 슬림 티셔츠",                                                       # 50000167 상위 분류
    "빈백 소파, 다다미, 어린이 독서 및 스트레스 해소용, 크림 향 두부 찌꺼기 무늬, 베이비 카운터, 베란다용, 누워서 쉴 수 있는 소파",  # 「향」→ 냉동고
    "우드 테라피 롤러 마사지 도구 1개 허리 목 어깨 허벅지 종아리 팔 바디 마사저 롤러 구아샤 안티 셀룰라이트",      # 「티」→ 멸치
    "제품 | 요시다 가방 홈페이지 | YOSHIDA & Co.",                                                    # 「가방」→ 남성가방>숄더백
    "큐브 매직큐브 RGB 조명 휴대용 무선 스피커 및 미니 무선 카드 삽입식 서브우퍼, 휴대폰, 태블릿, PC, TV, 야외 음악용 오디오 시스템 스피커",
    "해변에서 입기 좋은 심리스 스파게티 스트랩 탱크탑",                                                 # 「스트랩」→ 키링
    "YQ.STUDIO | 2026년 신상 반 고흐와 모네 명화 유화 팔찌, 여성용 고급 학생 액세서리",                  # 「팔찌」→ 키링
    # 삭제한 줄의 대표 낱말
    "스텐 텀블러", "캔들 디퓨저", "원예 전정가위", "멀티툴 나이프", "만년필 북마크", "EDC 피젯 스피너",
])
def test_deleted_rows_no_longer_decide(title):
    assert SS.match_category(title) == ""


def test_surviving_row_keyring():
    assert SS.match_details("과일 키링 아크릴")["leaf"] == "50000570"
