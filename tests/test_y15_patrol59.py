"""Y15 순찰 59(오너 2026-10-23 결정) — 네이버 옵션값 규칙 축약 3단계: ① 대괄호는 괄호만 ② 용도 수식어 ③ 색상+명사구 1개 · 영문·숫자 토큰 유지."""
from src.services.ai_fix import owner_short_steps, rule_short


def test_brackets_only_lose_the_brackets_d5af2185():
    # d5af2185 스스 보류 값(26자) — 원문 白色【夹灯版】宿舍床头
    v = "화이트 [스포트라이트 포함] 기숙사 침대 머리판"
    assert owner_short_steps(v) == "화이트 스포트라이트 포함 기숙사 침대 머리판"
    s, why = rule_short(v, {"검은색 스포트라이트 포함 기숙사 침대 머리판"})
    assert (s, why) == ("화이트 스포트라이트 포함 기숙사 침대 머리판", "")    # 같은 검사(절단·색상·숫자·형제 값) 통과


def test_usage_modifiers_go_before_cutting_nouns():
    v = "화이트 [기숙사용 독서등] 학생용 클립형 무선 충전 램프"            # ① 뒤에도 28자 → ② 용도 낱말만 뺀다
    assert owner_short_steps(v) == "화이트 독서등 클립형 무선 충전 램프"


def test_color_plus_one_phrase_keeps_brand_model_capacity_tokens():
    v = "블랙 [이동식 충전 Pro 버전] 4-in-1 멀티 포맷 · 6000mAh 양방향 충전"
    s = owner_short_steps(v)
    assert s == "블랙 이동식 Pro 4-in-1 6000mAh" and len(s) <= 25
    assert rule_short(v, set()) == (s, "")                                  # 영문·숫자 토큰을 잃지 않았다


def test_never_drops_tokens_to_fit_returns_nothing_instead():
    v = "블랙 [초대용량 Pro Max Ultra 버전] 20000mAh PD65W QC3.0 USB-C 고속 충전"
    assert owner_short_steps(v) == ""                                       # 토큰까지 25자 넘으면 자르지 않고 포기(옵션 탭·AI로)
    s, why = rule_short(v, set())
    assert why                                                              # 검사에서 떨어진 값은 저장되지 않는다


def test_rule_attempts_before_the_new_rules_get_one_more_try():
    from src.services import ai_fix as A
    ex = {"ai_fix_tried": {"option_short_rule:白色【夹灯版】宿舍床头": "2026-10-23T13:20:30+00:00",
                           "option_short_rule:新": A._now()}}
    assert not A._recently_tried(ex, "option_short_rule:白色【夹灯版】宿舍床头")     # 새 규칙 전에 떨어진 것 = 다시
    assert A._recently_tried(ex, "option_short_rule:新")                              # 새 규칙으로 떨어진 것 = 하루 대기


def test_rate_limited_image_check_is_unknown_not_a_block():
    """c44dde91(10-23 15:20): 상세 12장이 「응답 420」(alicdn 크롤 제한)으로 4곳 모두 막혔다 — 10-22엔 통과한 같은 주소."""
    from unittest.mock import patch
    from src.services import image_reachability as R
    from tests.test_d2b_cdn_and_reachability import _Resp, _sess
    for code in (420, 429):
        with patch("requests.Session", lambda code=code: _sess(head=_Resp(code, "text/html"))):
            r = R.check_one("https://img.alicdn.com/a.jpg")
        assert r["unknown"] is True and r["status"] == code and "속도 제한" in r["reason"]
        with patch("requests.Session", lambda code=code: _sess(head=_Resp(code, "text/html"))):
            assert R.check_all(["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"])["ok"] is True
    with patch("requests.Session", lambda: _sess(head=_Resp(404, "text/html"))):
        assert R.check_all(["https://img.alicdn.com/a.jpg"])["ok"] is False       # 진짜 없는 장은 그대로 막는다
