"""Y15(운영 10-21 14:10·14:20 사전검증 실측) — 네이버 옵션값 25자 축약 규칙·검사 구멍 3.

① 발판 74b78c42: 「분리세탁 · 커피 브라운 · 스노우 벨벳 - 다크 그린」(30자)이 규칙으로 26자까지만 — 띄운 「 - 」를 안 붙였다.
② 발판: AI 안 「스노우 벨벳-다크 그린」이 「단어 중간 절단(벨벳-그린)」 — 붙임표를 낱말 경계로 안 봤다.
③ 접이식 의자 81c61d46: 「[제품 높이 쿠션 포함, 기본 동일 색상 가죽 쿠션]」 → 「[제품 높이 쿠션 포함」(괄호 반쪽)이 규칙 축약으로 저장됐다.
"""
from src.collectors import ko_polish as K
from src.services import ai_fix as A


def test_rule_short_joins_spaced_hyphen_and_keeps_every_word():
    s, why = A.rule_short("분리세탁 · 커피 브라운 · 스노우 벨벳 - 다크 그린", set())
    assert why == "" and s == "분리세탁·커피 브라운·스노우 벨벳-다크 그린" and len(s) <= 25
    assert K.shorten("3-in-1 블랙 거치대", 25) == "3-in-1 블랙 거치대"            # 안 띄운 붙임표는 그대로


def test_hyphen_joined_words_are_not_a_cut():
    assert A.short_guard("스노우 벨벳 - 다크 그린 / 쿠션 / 발받침 미포함", "스노우 벨벳-다크 그린/발받침 미포함") == ""
    assert A.short_guard("천연 소가죽 블랙", "천연소 블랙").startswith("단어 중간 절단")      # 진짜 절단은 그대로 버림


def test_half_bracket_never_passes():
    v = "[제품 높이 쿠션 포함, 기본 동일 색상 가죽 쿠션]"
    assert K.shorten(v, 25) == "제품 높이 쿠션 포함"                               # 감싼 괄호를 벗김 · 반쪽 0
    assert A.short_guard(v, "[제품 높이 쿠션 포함") == "괄호 짝 안 맞음"
    assert K._balanced("(내장) [블랙]") and not K._balanced("[블랙") and not K._balanced("블랙)")


def test_repeated_word_dropped_but_set_word_still_guarded():
    assert K._drop_repeats("높이 44cm 화이트+높이 30cm 브라운/2개 세트") == "높이 44cm 화이트+30cm 브라운/2개 세트"
    s, why = A.rule_short("높이 44cm 화이트+높이 30cm 브라운/2개 세트", set())
    assert why == "지킬 말 빠짐(세트)"                                           # 26자라 뒤를 빼면 「세트」가 빠진다 — 정직 보류


def test_saved_half_bracket_fix_is_not_overlaid_and_is_dropped_for_retry():
    src = "【产品高度含坐垫 默认同色皮垫】"
    bad = "[제품 높이 쿠션 포함"
    ex = {"ai_fixes": {"option_short:" + src: {"kind": "option_short", "after": bad, "before": ""}},
          "option_value_overrides": {src: bad}}
    pd = {"option_value_overrides": {src: bad}, "skus": [{"spec": [src]}]}
    out = A.overlay(pd, ex)
    assert src not in (out.get("option_value_overrides") or {})
    assert A.drop_stale_short(ex, {"skus": [{"spec": [src]}]}) == ["option_short:" + src]
    assert "option_short:" + src not in A.fixes_of(ex) and src not in ex["option_value_overrides"]
