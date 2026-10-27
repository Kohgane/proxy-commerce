"""오너 지시 2026-10-27 22:20 ② — 「claim은 그렇게 하고」: 표시광고 과장·금칙 문구가 그대로 나가지 않게 등록 전에 자동으로 고친다.

- 상세 본문: 조각을 빼고 보낸다(`claim_removed`). 남은 글이 원래의 절반 아래면 저장된 AI 상세 초안(같은 조각도 뺀 것)으로
  채운다(`desc_refilled`) — 보류가 아니다. 초안이 없으면 `desc_refill_needed` → 사전검증이 초안부터 만든다.
- 상품명·옵션은 기존 길(사전검증 `ad_claim_risk` 보류 → 반려 자동 수정)이 고친다.
- 브랜드 블랙리스트 보류는 유지 — 보류 문구에 걸린 낱말을 원문 그대로.
"""
import json

import pytest


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    yield


def test_description_without_claims_is_untouched():
    from src.seller_console.upload_dispatcher import strip_claims
    pd = {"description": "원목 서랍장이에요.\n수납 3칸."}
    assert strip_claims(pd) == pd


def test_claim_fragments_are_removed_and_kept_text_stays():
    from src.collectors.ko_polish import ban_hits
    from src.seller_console.upload_dispatcher import strip_claims
    d = "원목 서랍장이에요. 손잡이는 둥글어요.\n최저가 30% 할인 쿠폰 5000\n수납 3칸이라 넉넉해요."
    out = strip_claims({"description": d})
    assert not ban_hits(out["description"]) and "원목 서랍장이에요" in out["description"] and "수납 3칸" in out["description"]
    assert set(out["claim_removed"]) >= {"최저가", "30% 할인", "쿠폰 5000"}
    assert "desc_refilled" not in out and "desc_refill_needed" not in out


def test_mostly_claims_is_refilled_from_the_ai_draft_not_held():
    from src.collectors.ko_polish import ban_hits
    from src.seller_console.upload_dispatcher import strip_claims
    draft = {"provider": "anthropic", "text": "원목으로 만든 서랍장이에요. 업계 1위 손잡이는 둥글고 수납이 넉넉해요."}
    out = strip_claims({"description": "최저가 30% 할인 업계 1위 쿠폰 5000 판매 1위", "detail_auto": draft})
    assert out["desc_refilled"] == "anthropic" and "원목으로 만든 서랍장" in out["description"]
    assert not ban_hits(out["description"])                                    # 초안에서도 같은 조각을 뺀다
    out = strip_claims({"description": "최저가 30% 할인 업계 1위 쿠폰 5000", "_detail_auto_saved": draft})
    assert out["desc_refilled"] == "anthropic"                                 # 갱신 경로(사본 칸)의 초안도 쓴다
    out = strip_claims({"description": "최저가 30% 할인 업계 1위 쿠폰 5000",
                        "detail_auto": {"provider": "stub", "text": "기본 문장"}})
    assert out.get("desc_refill_needed") is True and "desc_refilled" not in out   # AI 초안이 아니면 채우지 않는다


def test_dispatch_builder_sends_clean_description_with_the_saved_draft():
    from src.collectors.ko_polish import ban_hits
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    ex = {"detail_auto": {"provider": "openai", "text": "가볍고 튼튼한 접이식 의자예요. 캠핑에 좋아요."}}
    item = {"id": "i1", "title": "접이식 의자", "extra_json": json.dumps(ex, ensure_ascii=False)}
    pd = build_dispatch_payload({"title_ko": "접이식 의자", "description": "최저가 50% 할인 쿠폰 3000 업계 1위"}, item)
    assert not ban_hits(pd["description"]) and "접이식 의자예요" in pd["description"] and pd["desc_refilled"] == "openai"


def test_prevalidate_makes_a_draft_first_when_refill_has_nothing_to_use():
    from src.seller_console import views as V
    assert V._pv_claim_refill_needed({"description": "최저가 30% 할인 업계 1위 쿠폰 5000"}) is True
    assert V._pv_claim_refill_needed({"description": "원목 서랍장이에요. 최저가"}) is False
    assert V._pv_claim_refill_needed({"description": "최저가 30% 할인 쿠폰 5000",
                                      "detail_auto": {"provider": "anthropic", "text": "원목 서랍장이에요. 손잡이가 둥글어요."}}) is False
    assert V._pv_claim_refill_needed({"description": "최저가 30% 할인", "ai_detail_blocked": True}) is False


def test_risk_card_says_claims_are_fixed_automatically():
    from src.services import risk_gate as R
    h = next(x for x in R.scan({"title_ko": "원목 서랍장", "description": "최저가 30% 할인"})["hits"] if x["key"] == "claim")
    assert h["grade"] == "caution" and h["auto_fix"] and "자동으로 빼고 보내요" in h["why"]
    h = next(x for x in R.scan({"title_ko": "원목 서랍장 최저가"})["hits"] if x["key"] == "claim")
    assert "상품명·옵션은 사전검증에서 자동으로 고쳐요" in h["why"]


def test_blacklist_hold_stays_and_names_the_matched_words(monkeypatch):
    from src.services import risk_gate as R
    monkeypatch.setattr(R, "_blacklist", lambda: ["Supreme"])
    h = next(x for x in R.scan({"title_ko": "SUPREME 스타일 후드"})["hits"] if x["key"] == "blacklist")
    assert h["grade"] == "hold" and "「SUPREME」" in h["why"]                  # 원문 그대로(목록 표기 아님)
