"""Y11-L(오너 2026-10-14) — 다듬기 품목 맞춤 · 한자 남은 상자 재번역 · 글자 렌더 글꼴.

운영 실측(VRSUK 4ebaf1b8, 13:22~13:24 UTC 자동 다듬기):
- 21번(idx 20) 「软糯Q弹」 → 텐센트 「부드럽고 쫄깃한 식감」 — AI가 그대로 둠(라운지체어인데 식감). 프롬프트에 품목이 없었다.
- 22번(idx 21) 「O重力+]高弹定型绵自研「希尔丁体感系统」」 → 텐센트 「O중력+]고탄성 정형면 자研「希尔丁体感系统」」 — 한자 남음.
- 「글자 고치기」 렌더 7장 실패 「편집본 주소가 돌아오지 않았어요」 — Cloudinary `Unsupported font family Noto Sans KR`(400).
"""
from __future__ import annotations

import json

import pytest

VRSUK = {"title_ko": "VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 라운지체어",
         "options": [{"name": "颜色", "values_ko": ["오일 왁스 가죽 브라운", "오일 왁스 가죽 블랙"]}],
         "detail_specs": [["材质", "油蜡皮"], ["填充", "乳胶定型绵"]]}
BOX_21 = {"id": "t2", "src": "软糯Q弹", "tgt": "부드럽고 쫄깃한 식감"}
BOX_22 = {"id": "t7", "src": "O重力+]高弹定型绵自研「希尔丁体感系统」", "tgt": "O중력+]고탄성 정형면 자研「希尔丁体感系统」"}


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


def _ai(monkeypatch, reply):
    from src.ai import llm
    seen = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: seen.append(prompt) or {"text": reply(prompt)})
    return seen


def _ctx():
    from src.services import image_polish as P
    return {"title": VRSUK["title_ko"], "category": "", "rule": P.category_rule(VRSUK), "materials": P.materials(VRSUK)}


# ── 5. 품목·소재·품목별 금지 표현을 프롬프트에 ───────────────────────────────────────────────

def test_prompt_names_item_type_bans_and_materials(monkeypatch):
    from src.services import image_polish as P
    rule = P.category_rule(VRSUK)
    assert rule["key"] == "furniture" and rule["what"] == "리클라이너"
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t2", "ko": "부드럽고 탄탄한 쿠션감"}]}))
    r = P.polish_boxes([dict(BOX_21)], _ctx())
    prompt = seen[0]
    assert "이 상품은 가구(리클라이너)다" in prompt and "식감" in prompt and "착용감" in prompt and "쿠션감" in prompt
    assert "소재·옵션: 오일 왁스 가죽 브라운" in prompt and "材质: 油蜡皮" in prompt
    row = r["rows"][0]
    assert row["ko"] == "부드럽고 탄탄한 쿠션감" and row["from"] == "polish"


def test_other_category_words_are_rejected(monkeypatch):
    """AI가 식감을 그대로 두면 버리고 사유를 남긴다(그 상자는 텐센트 글자 — 편집 화면 「다듬기」 줄에 보인다)."""
    from src.services import image_polish as P
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t2", "ko": "말랑하고 쫄깃한 식감"}]}))
    row = P.polish_boxes([dict(BOX_21)], _ctx())["rows"][0]
    assert row["from"] == "tencent" and row["why"] == "다른 품목 표현(식감)"


def test_category_from_code_when_title_has_no_word():
    from src.services import image_polish as P
    assert P.category_rule({"title_ko": "젤리 사탕 모음"})["key"] == "food"
    assert P.category_rule({"title_ko": "XYZ 세트", "category_code": "BTY"})["key"] == "beauty"
    assert P.category_rule({"title_ko": "XYZ 세트"}) == {}


# ── 6. 한자 남은 상자 = 번역 안 됨 → 원문 전체 새로 번역 · 결과줄 「한자 잔존 n상자 재번역」 ─────────────────────

def test_han_left_box_is_sent_as_redo_and_counted(monkeypatch):
    from src.services import image_polish as P
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t7", "ko": "무중력 고탄성 정형 폼 · 자체 개발 「힐딩 체감 시스템」"}]}))
    r = P.polish_boxes([dict(BOX_22)], _ctx())
    sent = [json.loads(l) for l in seen[0].splitlines() if l.startswith("{")]
    assert sent == [{"id": "t7", "src": BOX_22["src"], "mt": "", "redo": True}]       # 한자 섞인 기계 번역은 주지 않는다
    row = r["rows"][0]
    assert row["han_left"] and row["from"] == "polish" and not P.han_left(row["ko"])


def test_output_with_han_is_rejected(monkeypatch):
    from src.services import image_polish as P
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t7", "ko": "고탄성 정형면 자研"}]}))
    row = P.polish_boxes([dict(BOX_22)], _ctx())["rows"][0]
    assert row["why"] == "한자가 남음" and row["from"] == "tencent"


def test_result_line_says_han_retranslated():
    from src.services import image_polish as P
    ex = {"detail_images_ko": [{"idx": 21, "polish": {"changed": 3, "calls": 1, "han_left": 2, "han_fixed": 1, "rows": []}},
                               {"idx": 20, "polish": {"changed": 1, "calls": 1, "rows": []}}]}
    assert P.item_line("x", ex) == "번역 다듬기 2장: 바뀐 상자 4 · AI 2회 · 한자 잔존 1상자 재번역(못 고친 1)"


def test_polish_entry_records_han_and_rule(monkeypatch):
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = dict(VRSUK, detail_images=["https://img/d.jpg"] * 22, detail_images_ko=[{
        "idx": 21, "status": "done", "use": True, "vendor": "tencent", "url": "https://res.cloudinary.com/x/t21.jpg",
        "translated_url": "https://res.cloudinary.com/x/t21.jpg", "box_size": [1440, 1800], "box_frame": "identity",
        "boxes": [{"x": 10, "y": 10, "w": 500, "h": 40, "src": BOX_22["src"], "tgt": BOX_22["tgt"]}]}])
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t0", "ko": "고탄성 정형 폼 「힐딩 체감 시스템」"}]}))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "apply", lambda extra, kind, idx, ops, by="user", small=None: {"ok": True, "version": "edit:1"})
    P.polish_entry(ex, "detail", 21)
    pl = ex["detail_images_ko"][0]["polish"]
    assert pl["han_left"] == 1 and pl["han_fixed"] == 1 and pl["rule"] == "furniture"


# ── 렌더 글꼴: Cloudinary가 받는 글꼴 · 실패 사유를 남긴다 ─────────────────────────────────────────

def test_text_layer_uses_font_cloudinary_accepts():
    from src.services import image_edit as IE
    layer = IE._text_layer("부드럽고 탄탄한 쿠션감", {"x": 0, "y": 0, "w": 400, "h": 40}, "333333")
    assert layer.startswith("l_text:NanumGothic_") and "Noto" not in layer


def test_eager_failure_reason_is_kept(monkeypatch):
    from src.media import image_pipeline as IPL
    from src.services import image_edit as IE
    ex = {"images": ["https://img/g0.jpg"], "images_ko": [{
        "idx": 0, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/t0.jpg", "translated_url": "https://res.cloudinary.com/x/t0.jpg",
        "box_size": [800, 800], "box_frame": "identity", "boxes": [{"x": 10, "y": 10, "w": 300, "h": 40, "src": "软糯", "tgt": "식감"}]}]}
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "_load_small", lambda url: (None, (800, 800)))
    monkeypatch.setattr(IPL, "upload_remote", lambda *a, **k: {"ok": True, "eager": [{"status": "failed", "reason": "Unsupported font family X"}],
                                                               "keys": ["eager", "public_id"]})
    r = IE.apply(ex, "gallery", 0, [{"id": "t0", "action": "text", "text": "쿠션감"}], by="polish")
    assert not r["ok"] and r["error"] == "편집본을 만들지 못했어요 — Unsupported font family X"
