"""Y11-I(오너 2026-10-14) — 번역 다듬기(자동): 텐센트 상자 글자를 haiku로 다듬어 「번역본(다듬음)」 버전을 만든다.

재현(VRSUK 운영 상자): 상세 13 「프로피리티어 20」(원문 Proprietary 20) · 상세 8 「자리 Eams」(원문 Chair Eams) · 상세 17 「아만 평연 봉선」(亚曼平韧缝线).
반례: AI가 「최고·1위·100%」를 만들면 Y10 금지어 — 그런 상자 결과는 버린다(텐센트 글자 그대로).
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


def _ai(monkeypatch, reply):
    """haiku 가짜 — 받은 프롬프트를 적고 `reply(prompt)`를 돌려준다."""
    from src.ai import llm
    seen = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: seen.append((prompt, k)) or {"text": reply(prompt)})
    return seen


BOXES = [{"id": "t0", "src": "拓荒者 20", "tgt": "개척자 20"},
         {"id": "t1", "src": "伊姆斯椅子", "tgt": "자리 Eams"},
         {"id": "t2", "src": "暗面平沿缝线", "tgt": "아만 평연 봉선"}]


# ── 1. 용어집 선적용(AI 없어도) ───────────────────────────────────────────────────────────────

def test_glossary_preapplied_to_tencent_text():
    from src.services import image_polish as P
    assert P.apply_glossary("拓荒者 20", "개척자 20") == "선구자 20"
    assert P.apply_glossary("伊姆斯椅子", "자리 Eams") == "의자 Eams"
    assert P.apply_glossary("曲木", "곡목 합판") == "곡목 합판"            # 이미 바른 말 — 두 번 안 붙인다
    assert P.apply_glossary("沙发", "자리") == "자리"                       # 원문에 椅子가 없으면 손대지 않는다
    assert P.apply_glossary("Chair Eams", "자리 Eams") == "의자 Eams"      # 실측 상세 8 — 원문은 영어 Chair
    terms = {P._srcs(t)[0]: t["ko"] for t in P.glossary()}
    assert terms["油蜡皮"] == "오일 왁스 가죽" and terms["胡桃木"] == "호두나무" and terms["铝合金"] == "알루미늄 합금"
    assert terms["乳胶"] == "라텍스" and terms["曲木"] == "곡목 합판" and terms["先驱"] == "선구자"


def test_without_ai_only_glossary(monkeypatch):
    from src.ai import llm
    from src.services import image_polish as P
    monkeypatch.setattr(llm, "anthropic_ready", lambda: False)
    r = P.polish_boxes([dict(b) for b in BOXES], {"title": "라운지 체어"})
    by = {x["id"]: x for x in r["rows"]}
    assert by["t0"]["ko"] == "선구자 20" and by["t0"]["from"] == "glossary"
    assert by["t2"]["ko"] == "아만 평연 봉선" and by["t2"]["from"] == "tencent"
    assert r["calls"] == 0 and "용어집만" in r["ai_why"]


# ── 2. haiku 한 번(상자 10개 이하) · 프롬프트에 상품명·카테고리·용어집·금지어 ───────────────────────────────

def test_one_call_per_ten_boxes_with_context(monkeypatch):
    from src.services import image_polish as P
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t0", "ko": "선구자 20"}, {"id": "t1", "ko": "임스 의자"},
                                                              {"id": "t2", "ko": "은박 평면 스티치"}]}))
    r = P.polish_boxes([dict(b) for b in BOXES], {"title": "VRSUK 리클라이너", "category": "거실 의자"})
    assert len(seen) == 1 and r["calls"] == 1
    prompt, kw = seen[0]
    assert "VRSUK 리클라이너" in prompt and "거실 의자" in prompt and "拓荒者→선구자" in prompt and "1위" in prompt
    assert kw["size"] == "small" and kw["providers"] == ["anthropic"]
    by = {x["id"]: x for x in r["rows"]}
    assert by["t2"]["ko"] == "은박 평면 스티치" and by["t2"]["from"] == "polish"
    many = [{"id": f"t{i}", "src": "椅子", "tgt": "의자"} for i in range(23)]
    seen.clear()
    P.polish_boxes(many, {})
    assert len(seen) == 3                                                  # 10 · 10 · 3


# ── 3. 반례: 과장·금지어·숫자 누락·없던 상표는 버린다 ───────────────────────────────────────────────

@pytest.mark.parametrize("ko,why", [("업계 1위 선구자 20", "금지어"), ("최고의 선구자 20", "금지어"),
                                    ("100% 선구자 20", "금지어"), ("선구자", "숫자 누락"),
                                    ("허먼밀러 선구자 20", "없던 상표")])
def test_bad_output_is_discarded(monkeypatch, ko, why):
    from src.services import image_polish as P
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t0", "ko": ko}]}))
    r = P.polish_boxes([dict(BOXES[0])], {})
    row = r["rows"][0]
    assert row["ko"] == "선구자 20" and row["from"] == "glossary"          # 텐센트(+용어집) 그대로
    assert why in row["why"] and row["ai"] == ko


def test_blank_means_erase(monkeypatch):
    from src.services import image_polish as P
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t2", "ko": ""}]}))
    row = P.polish_boxes([dict(BOXES[2])], {})["rows"][0]
    assert row["ko"] == "" and row["from"] == "polish"


def test_daily_cap(monkeypatch):
    from src.services import image_polish as P
    monkeypatch.setenv("IMAGE_POLISH_DAILY_CAP", "1")
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": []}))
    P.polish_boxes([dict(b) for b in BOXES], {})
    r = P.polish_boxes([dict(b) for b in BOXES], {})
    assert len(seen) == 1 and "상한(1회)" in r["ai_why"] and P.today_count() == 1


# ── 4. 버전: 번역본(다듬음) 새 편집본 · 텐센트 번역본은 남는다 · 기본 선택 다듬은 쪽 ───────────────────────────

def _ex():
    return {"title_ko": "VRSUK 리클라이너", "detail_images": ["https://img/d0.jpg"],
            "detail_images_ko": [{"idx": 0, "status": "done", "use": True, "vendor": "tencent",
                                  "url": "https://res.cloudinary.com/x/t0.jpg", "translated_url": "https://res.cloudinary.com/x/t0.jpg",
                                  "box_size": [800, 800], "box_frame": "identity",
                                  "boxes": [{"x": 10, "y": 10, "w": 300, "h": 40, "src": "拓荒者 20", "tgt": "개척자 20"},
                                            {"x": 10, "y": 100, "w": 300, "h": 40, "src": "伊姆斯椅子", "tgt": "자리 Eams"}]}]}


def test_polish_entry_makes_polished_version(monkeypatch):
    from src.services import image_edit as IE
    from src.services import image_polish as P
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t0", "ko": "선구자 20"}, {"id": "t1", "ko": "임스 의자"}]}))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []

    def _apply(extra, kind, idx, ops, by="user", small=None):
        applied.append((ops, by))
        e = IE._entry(extra, kind, idx)
        e.setdefault("edits", []).append({"n": 1, "url": "https://res.cloudinary.com/x/p1.jpg", "base_key": "translated", "by": by,
                                          "render": "local", "render_v": IE.RENDER_V})
        e["url"] = "https://res.cloudinary.com/x/p1.jpg"
        return {"ok": True, "version": "edit:1", "pending": False}
    monkeypatch.setattr(IE, "apply", _apply)
    ex = _ex()
    r = P.polish_entry(ex, "detail", 0)
    assert r["ok"] and r["changed"] == 2
    ops, by = applied[0]
    assert by == "polish" and {o["text"] for o in ops} == {"선구자 20", "임스 의자"}
    vs = {v["key"]: v["label"] for v in IE.versions(ex, "detail", 0)}
    assert vs["translated"] == "번역본" and vs["edit:1"] == "번역본(다듬음)"         # 텐센트 번역본은 남는다
    assert IE.current_key(ex["detail_images_ko"][0]) == "edit:1"                       # 기본 선택 = 다듬은 쪽
    assert P.polish_entry(ex, "detail", 0)["why"].startswith("번역본이 지금 버전이 아님")  # 두 번 안 함
    pv = IE._polish_view(ex["detail_images_ko"][0])
    assert {(x["tgt"], x["ko"]) for x in pv["rows"]} == {("개척자 20", "선구자 20"), ("자리 Eams", "임스 의자")}


def test_polish_never_touches_user_chosen_version(monkeypatch):
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _ex()
    ex["detail_images_ko"][0]["use"] = False                                  # 사용자가 원본으로 골랐다
    seen = _ai(monkeypatch, lambda p: "{}")
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    assert P.polish_entry(ex, "detail", 0)["ok"] is False and not seen


def test_worker_runs_polish_after_translation(monkeypatch):
    """큐 워커: 번역(상자 있음) 저장 직후 다듬기를 부른다 · 다듬기가 실패해도 번역 결과는 done."""
    from src.seller_console import collect_history_store as S
    from src.services import image_polish as P
    from src.services import image_translate_auto as A
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11i",
                   title="x", price="1", currency="CNY", extra={"detail_images": ["https://img/d0.jpg"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    entry = dict(_ex()["detail_images_ko"][0])
    monkeypatch.setattr(A, "translate_page", lambda *a, **k: dict(entry))
    calls = []
    monkeypatch.setattr(P, "polish_job", lambda *a: calls.append(a))
    st, _why = A._translate_job({"item_id": iid, "kind": "detail", "idx": 0, "user_id": "y11i"})
    assert st == "done" and calls and calls[0][2:] == ("detail", 0)


def test_counter_beside_tencent_line(monkeypatch):
    from src.services import image_translate_auto as A
    line = A.queue_line("")
    assert line["polish_cap"] == 400 and line["polish_today"] == 0
