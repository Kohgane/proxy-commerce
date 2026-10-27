"""순찰 123(오너 2026-10-26 21:18 「이거 뭐 제품 하나하나마다 다 수정을 해나가야 하는 거냐」) — 보류를 사람에게 묻지 않고 자동 처리.

실측(MOFT 거치대 f2b5df5d, 6마켓 보류): 호환 표기 Apple Watch(상세 21) → 6마켓마다 「빼고 등록·그래도 등록·등록 안 함」 고르라고 멈춤,
그 뒤에야 AI 자동수정(카테고리·옵션 축약)이 돈다. 쿠팡 대표 사진 글자도 「다른 장을 고르거나 그래도 등록」.
계약: ① 상표·호환 표기 보류는 처음 보는 낱말도 기본 「빼고 등록」 자동(기록 auto=True·first_time, 카드에서 되돌릴 수 있음)
     ② RISK_AUTO_STRIP=0이면 예전처럼 기억된 낱말만 ③ 쿠팡 대표에 글자면 글자 없는 다음 갤러리 장을 자동으로 대표로(사람 결정은 안 건드림).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setattr(R, "learned", lambda: {})
    monkeypatch.setattr(R, "allowlist", lambda: set())
    monkeypatch.setattr(R, "_learn", lambda *a, **k: None)


def _ex():
    return {"title_ko": "Apple Watch 호환 스마트 테이블 매트", "keywords": ["애플워치", "거치대"], "description_ko": "Apple Watch 충전 거치 가능",
            "images": ["https://img.example/a.jpg", "https://img.example/b.jpg", "https://img.example/c.jpg"]}


def test_compat_hold_is_auto_stripped_first_time(monkeypatch):
    from src.services import risk_gate as R
    ex = _ex()
    sc = R.scan(ex)
    compat = [h for h in sc["hits"] if h["key"].startswith("compat:")]
    assert compat and compat[0]["grade"] != "caution", [h["key"] for h in sc["hits"]]
    monkeypatch.delenv("RISK_AUTO_STRIP", raising=False)
    done = R.auto_apply(ex, by="t")
    assert any("Apple" in d or "호환" in d for d in done), done
    d = ex["risk_decisions"][compat[0]["key"]]
    assert d["action"] == "strip" and d["auto"] is True and d["default"] == "first_time"
    assert not R.holds(R.scan(ex))                                 # 보류 0 — 사람이 고를 게 없다
    assert "Apple Watch" not in ex["title_ko"]


def test_legacy_ask_mode_env(monkeypatch):
    from src.services import risk_gate as R
    ex = _ex()
    monkeypatch.setenv("RISK_AUTO_STRIP", "0")
    assert R.auto_apply(ex, by="t") == []
    assert R.holds(R.scan(ex))                                     # 예전처럼 묻는다


def test_auto_strippable_covers_compat_but_not_cert():
    from src.services import risk_gate as R
    assert R._auto_strippable("tm:레고") and R._auto_strippable("compat:apple_watch")
    assert not R._auto_strippable("cert:kc") and not R._auto_strippable("claim")


def test_auto_rep_pick_swaps_to_text_free_image(monkeypatch):
    from src.services import coupang_image_check as C
    monkeypatch.setattr(C, "enabled", lambda: True)
    flags = {"https://img.example/a.jpg": [{"key": "text", "hold": True, "line": "텍스트 있음"}],
             "https://img.example/b.jpg": [{"key": "text", "hold": True, "line": "텍스트 있음"}],
             "https://img.example/c.jpg": []}
    monkeypatch.setattr(C, "check_url", lambda u: {"state": "done", "flags": flags.get(u, [])})
    ex = _ex()
    out = C.auto_rep_pick(ex, images_effective=list(ex["images"]), by="t")
    assert out["changed"] and out["picked_idx"] == 2
    assert ex["rep_image"] == "https://img.example/c.jpg" and ex["rep_auto_pick"]["from"] == "https://img.example/a.jpg"
    # 사람이 정한 대표는 안 건드린다
    ex2 = dict(_ex(), rep_image="https://img.example/b.jpg")
    assert C.auto_rep_pick(ex2, images_effective=["https://img.example/b.jpg"], by="t")["why"] == "사람이 정한 대표"
    # 전부 글자면 바꾸지 않는다(보류는 사람에게)
    monkeypatch.setattr(C, "check_url", lambda u: {"state": "done", "flags": [{"key": "text", "hold": True, "line": "x"}]})
    ex3 = _ex()
    assert C.auto_rep_pick(ex3, images_effective=list(ex3["images"]), by="t")["changed"] is False and "rep_image" not in ex3


def test_effective_images_follow_auto_rep():
    from src.services import image_translate_store as S
    ex = _ex()
    ex["rep_image"] = ex["images"][2]
    eff = S.effective_images(ex, originals=list(ex["images"]))
    assert eff and eff[0].endswith("c.jpg")
