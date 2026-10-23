"""Y14-d — 네이버 옵션값 25자 축약: AI 안이 검사에서 떨어지면 규칙 축약(`ko_polish.shorten`, AI 호출 없음)으로.

실측(10-20 17:00 재사전검증 · 3-in-1 맥세이프 거치대): 「3-in-1 블랙 휴대폰 이어폰 거치대(내장 충전기)」(29자) →
AI 「블랙 이어폰 거치대(내장 충전기)」 → 검사 「지금 값의 숫자·영문 빠짐(3-in-1)」으로 버림(가드는 맞다) → 네이버 2곳 보류 그대로,
그리고 하루 동안 다시 안 묻는다. 규칙 축약기는 이미 있었다(「충전기 내장 3-in-1 블랙 거치대」 20자) — 네이버 25자 보류엔 안 쓰였다.
"""
from datetime import datetime, timezone

from src.services import ai_fix as A

_V = "3-in-1 블랙 휴대폰 이어폰 거치대(내장 충전기)"
_W = "3-in-1 화이트 휴대폰 이어폰 거치대(내장 충전기)"


def test_rule_short_passes_same_guards():
    s, why = A.rule_short(_V, set())
    assert why == "" and len(s) <= 25 and "3-in-1" in s and "블랙" in s
    # 형제 값과 같아지면 다음 규칙(순찰 59 오너 3단계)으로 — 그것도 같아지면 버린다
    s2, why2 = A.rule_short(_V, {s})
    assert why2 == "" and s2 == A.owner_short_steps(_V) and s2 != s
    assert A.rule_short(_V, {s, s2})[1] == "다른 옵션 값과 같아짐"


def _setup(monkeypatch):
    monkeypatch.setattr(A, "long_option_values", lambda pd, cap=0: [{"src": "黑色3合1", "ko": _V}, {"src": "白色3合1", "ko": _W}])
    monkeypatch.setattr(A, "all_option_values", lambda pd: [_V, _W])
    monkeypatch.setattr(A, "drop_stale_short", lambda ex, pd: [])
    calls = []
    monkeypatch.setattr(A, "_call", lambda task, pd: calls.append(task["kind"]) or {})
    return calls


def test_ai_rejected_values_get_rule_short_without_ai_call(monkeypatch):
    calls = _setup(monkeypatch)
    now = datetime.now(timezone.utc).isoformat()
    ex = {"ai_fix_tried": {"option_short:黑色3合1": now, "option_short:白色3合1": now},
          "ai_fix_rejects": {"option_short:黑色3合1": "지금 값의 숫자·영문 빠짐(3-in-1)"}}
    pd = {}
    results = [{"market": "smartstore:chezgoga", "ok": False, "fixes": ["option_short"]}]
    kinds = [t["kind"] for t in A.plan(pd, ex, results)]
    assert kinds == ["option_short_rule"]                       # AI 축약은 하루 대기 · 규칙만
    out = A.run_round(pd, ex, results, calls_left=6)
    assert calls == [] and out["calls"] == 0                    # AI 호출 없음
    ov = ex["option_value_overrides"]
    assert set(ov) == {"黑色3合1", "白色3合1"} and ov["黑色3合1"] != ov["白色3合1"]
    assert all(len(v) <= 25 and "3-in-1" in v for v in ov.values())
    assert out["markets"] == ["smartstore:chezgoga"]            # 같은 잡에서 다시 잰다
    fx = ex["ai_fixes"]["option_short:黑色3合1"]
    assert fx["provider"] == "rule" and "규칙 축약" in fx["why"]
    # 다음 회전엔 다시 계획하지 않는다(적용됨)
    assert not [t for t in A.plan(pd, ex, results) if t["kind"].startswith("option_short")]


def test_ai_answer_rejected_falls_back_to_rule_in_same_round(monkeypatch):
    """AI 안이 떨어지면 `_apply`는 그대로 적용 0(기존 계약) · `run_round`가 같은 회전에서 그 값만 규칙 축약."""
    _setup(monkeypatch)
    monkeypatch.setattr(A, "long_option_values", lambda pd, cap=0: [{"src": "黑色3合1", "ko": _V}])
    monkeypatch.setattr(A, "_call", lambda task, pd: {"json": {"values": {_V: "블랙 이어폰 거치대(내장 충전기)"}},
                                                      "provider": "anthropic", "model": "m", "usd": 0.001})
    ex, pd = {}, {}
    results = [{"market": "smartstore:gocosmos", "ok": False, "fixes": ["option_short"]}]
    out = A.run_round(pd, ex, results, calls_left=6)
    assert out["calls"] == 1 and out["applied"] == ["option_short:黑色3合1"] and out["markets"] == ["smartstore:gocosmos"]
    assert "3-in-1" in ex["option_value_overrides"]["黑色3合1"] and ex["ai_fixes"]["option_short:黑色3合1"]["provider"] == "rule"
    assert any("숫자·영문 빠짐" in x for x in out["log"]) and any("규칙" in x for x in out["log"])


def test_short_guard_suffix_yong_and_measure_first_word():
    """Y14(운영 10-21 다음 5건 사전검증): AI 축약이 검사 오탐으로 버려졌다.
    ① 「성인용 …」→「성인 …」(허리 보호 소파) — 「~용」 꼬리 떼기는 단어 절단이 아니다.
    ② 「높이 44cm 화이트+높이 30cm 브라운/2개 세트」(접이식 의자) — 첫 낱말 「높이」는 색상이 아니다(색 낱말은 여전히 지킨다)."""
    from src.services.ai_fix import short_guard
    assert short_guard("성인용 새싹 그린 (의자발 캡 포함) 좌고 41cm", "성인 새싹그린 캡포함 좌고41cm") == ""
    assert short_guard("높이 44cm 화이트+높이 30cm 브라운/2개 세트", "44cm 화이트+30cm 브라운 세트") == ""
    assert "화이트" in short_guard("높이 44cm 화이트+높이 30cm 브라운/2개 세트", "44cm+30cm 브라운 세트")   # 색은 지킨다
    assert "세트" in short_guard("높이 44cm 화이트+높이 30cm 브라운/2개 세트", "44cm 화이트+30cm 브라운")     # 지킬 말 그대로
