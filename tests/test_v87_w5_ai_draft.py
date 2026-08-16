"""tests/test_v87_w5_ai_draft.py — v87-W5 AI 상세 초안 생성 품질(번역 이상 수리).

## 오너 실기기 결함(재조사 금지)
라쿠텐 TSUMUGI 레코드(일본어 원문 상세)에서 [AI 상세 초안 생성] → "번역이 되는데 좀 이상함".
언어 원칙(불변): KO/EN(JP) 혼재 금지. 초안은 **판매용 한국어 문안**이 기대치(원문 직역 덤프 아님).

## 근원 (재현으로 특정)
1. **입력 오염 미제거**: 라쿠텐 UI 문구(不適切な商品を報告·レビュー·お気に入り·送料無料 등)가 detail_specs/
   keywords에 섞여 초안에 그대로 유입. `_CONTAM_RE`는 확장/브라우저 크롬만 잡고 **마켓 UI 쓰레기(특히
   일본어)는 미포함**, 게다가 스펙에는 오염 필터가 **아예 미적용**이었다.
2. **한국어 정규화 미강제**: OpenAI 프롬프트가 "확인된 정보만"만 지시하고, "입력이 외국어일 수 있으니 전부
   자연스러운 한국어로, 원문 조각·스펙 직역 금지"를 명시하지 않아 일본어 스펙이 그대로/직역돼 KO 혼재.

## 수리 (서버만 — 확장·번역쿼터·AI예산 불가침)
- `_clean_specs_for_draft`/`_clean_keywords_for_draft` + `_MARKET_UI_JUNK_RE`(JP/KO/EN UI 액션·배너만 좁게)로
  스펙/키워드에서 UI 쓰레기 제거(상품 속성어 サイズ/素材/원산지/색상/무게는 보존). 초안 입력 전처리.
- OpenAI 프롬프트에 **한국어 정규화 + UI 문구 무시** 지시 추가(외국어 입력 → 처음부터 끝까지 한국어 판매 문안).
"""
from __future__ import annotations

import pytest

from src.seller_console.ai import translator as T
from src.seller_console.ai.translator import (
    AITranslator, _clean_specs_for_draft, _clean_keywords_for_draft, _is_ui_junk,
)

_TSUMUGI = {
    "title": "TSUMUGI 紬 レコード 木製ケース", "category": "GEN", "brand": "TSUMUGI",
    "keywords": ["レコード", "木製", "紬", "レビューを見る", "送料無料"],
    "specs": [
        ["サイズ", "約30×30×5cm"], ["素材", "天然木（オーク）"], ["原産国", "日本"],
        ["不適切な商品を報告", "する"], ["レビュー", "レビューを書く"], ["お気に入り", "お気に入りに追加"],
    ],
    "options": [{"name": "カラー", "values": ["ナチュラル", "ブラウン"]}],
}
_JUNK = ["不適切な商品を報告", "お気に入りに追加", "レビューを書く", "送料無料", "レビューを見る"]


# ── UI 쓰레기 판별 + 스펙/키워드 정제 ─────────────────────────────────
def test_ui_junk_detects_marketplace_actions_not_real_specs():
    for j in ("不適切な商品を報告", "レビューを書く", "お気に入りに追加", "送料無料",
              "장바구니", "리뷰 쓰기", "무료 배송", "add to cart", "write a review", "free shipping"):
        assert _is_ui_junk(j), f"UI 쓰레기 미탐: {j}"
    # 진짜 상품 속성은 보존(오탐 0).
    for real in ("サイズ", "素材", "原産国", "약 30×30×5cm", "天然木", "カラー", "重量 1.2kg", "색상", "소재"):
        assert not _is_ui_junk(real), f"상품 속성 오탐: {real}"


def test_clean_specs_drops_junk_rows_keeps_real():
    cleaned = _clean_specs_for_draft(_TSUMUGI["specs"])
    labels = [l for l, _ in cleaned]
    assert "サイズ" in labels and "素材" in labels and "原産国" in labels   # 실 스펙 보존
    assert not any(_is_ui_junk(l) or _is_ui_junk(v) for l, v in cleaned)   # UI 쓰레기 0
    assert len(cleaned) == 3


def test_clean_keywords_drops_ui_junk():
    kws = _clean_keywords_for_draft(_TSUMUGI["keywords"])
    assert "レビューを見る" not in kws and "送料無料" not in kws
    assert "レコード" in kws and "木製" in kws


# ── 초안 출력에 UI 쓰레기 0 (stub 경로 결정적) ─────────────────────────
def test_draft_output_has_no_ui_junk(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    out = AITranslator().generate_description(_TSUMUGI)
    assert out["provider"] == "stub"
    for j in _JUNK:
        assert j not in out["text"], f"초안에 UI 쓰레기 잔존: {j}"


# ── OpenAI 프롬프트: 한국어 정규화 + UI 무시 + 정제된 입력 (런타임 캡처, 실호출 0) ──
def test_openai_prompt_forces_korean_and_ignores_junk(monkeypatch):
    import requests

    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": "한국어 초안"}}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        return _Resp()

    monkeypatch.setattr(requests, "post", _fake_post)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-QA")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    tr = AITranslator()
    tr.provider = "openai"   # 프로바이더 강제(키 세팅됨)
    res = tr.generate_description(_TSUMUGI)
    assert res["provider"] == "openai"
    p = captured["prompt"]
    # 한국어 정규화 + UI 무시 지시가 프롬프트에 있어야 한다.
    assert "자연스러운 한국어 판매 문안" in p
    assert "직역하지 마세요" in p or "직역하지" in p
    assert "UI 문구" in p and "무시" in p
    # 정제된 입력만 프롬프트에 들어간다(UI 쓰레기 0).
    for j in _JUNK:
        assert j not in p, f"프롬프트에 UI 쓰레기 유입: {j}"
    # 실 스펙은 남아 있다(정보 손실 0).
    assert "サイズ" in p and "原産国" in p
