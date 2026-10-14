"""Y11-L 보강(오너 2026-10-14) — 다듬기 저장 실패 · AI 캐시 · 상세 타일 편집 · 글자 넘침.

운영 실측 13:03~13:05 UTC VRSUK 「번역 다듬기」: 결과줄 「편집본 주소가 돌아오지 않았어요 — 응답 키: api_key, asset_folder, …」.
코드는 업로드 응답의 `eager[].secure_url|url`(파생본)을 찾는다 — 맨 위 `secure_url`은 **편집 전 업로드**라 쓰면 가짜 성공.
파생본이 없던 이유 = 글자 오버레이 글꼴 거부(`Unsupported font family Noto Sans KR`, 직접 재현).
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


def _ex():
    return {"title_ko": "VRSUK 리클라이너", "images": ["https://img/g0.jpg"], "images_ko": [{
        "idx": 0, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/image/upload/v1/t0.jpg",
        "translated_url": "https://res.cloudinary.com/x/image/upload/v1/t0.jpg", "box_size": [800, 800], "box_frame": "identity",
        "boxes": [{"x": 10, "y": 10, "w": 400, "h": 60, "src": "软糯Q弹", "tgt": "부드럽고 쫄깃한 식감"}]}]}


# ── 1. 렌더: Y11-M부터 우리 쪽에서 그려 일반 업로드 — 변환 주소 조립 경로는 없다(test_y11m_local_render) ─────────────

def test_transform_url_path_is_gone():
    from src.services import image_edit as IE
    for gone in ("build_transform", "_text_layer", "_ready", "_LAST_CLD", "FONT"):
        assert not hasattr(IE, gone), gone


# ── 반례: 글자가 상자보다 길면 — 폭 기준 축소 + 줄바꿈, 텐센트 글자보다 많이 작아지면 텐센트 글자 유지 「길어서 유지」 ────────

def test_text_fit_two_lines_and_too_long():
    from src.services import image_edit as IE
    f = IE.text_fit("부드럽고 탄탄한 쿠션감", {"w": 300, "h": 120}, ref="부드럽고 쫄깃한 식감")
    assert len(f["lines"]) == 2 and f["fits"]
    assert not IE.text_fit("아주 아주 긴 다듬은 문장이 상자 하나에 도저히 들어가지 않는 경우입니다", {"w": 120, "h": 30}, ref="짧은 글")["fits"]


def test_polish_keeps_tencent_when_too_long(monkeypatch):
    from src.ai import llm
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _ex()
    ex["images_ko"][0]["boxes"][0].update(w=120, h=30)
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda p, **k: {"text": json.dumps({"boxes": [{"id": "t0", "ko": "아주 부드럽고 탄탄하게 몸을 받쳐 주는 고밀도 쿠션감과 지지감"}]})})
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []
    monkeypatch.setattr(IE, "apply", lambda *a, **k: applied.append(a) or {"ok": True, "version": "edit:1"})
    r = P.polish_entry(ex, "gallery", 0)
    pl = ex["images_ko"][0]["polish"]
    assert pl["too_long"] == 1 and not applied and r["changed"] == 0
    assert pl["rows"][0]["why"].startswith("길어서 유지")
    assert "길어서 유지 1" in P.item_line("x", ex)


# ── 2. AI 캐시: 렌더만 다시 할 때 AI를 다시 안 부른다 ───────────────────────────────────────

def test_rerun_uses_cache_zero_ai_calls(monkeypatch):
    from src.ai import llm
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _ex()
    calls = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda p, **k: calls.append(1) or {"text": json.dumps({"boxes": [{"id": "t0", "ko": "부드럽고 탄탄한 쿠션감"}]})})
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "apply", lambda *a, **k: {"ok": False, "error": "편집본을 만들지 못했어요 — Unsupported font family Noto Sans KR"})
    P.polish_entry(ex, "gallery", 0)                                             # 첫 판: AI 1회 · 렌더 실패
    assert len(calls) == 1
    monkeypatch.setattr(IE, "apply", lambda *a, **k: {"ok": True, "version": "edit:1"})
    r = P.polish_entry(ex, "gallery", 0)                                         # 글꼴 고친 뒤 다시: 캐시
    assert len(calls) == 1 and r["calls"] == 0 and r["cached"] == 1 and r["changed"] == 1
    assert P.item_line("x", ex) == "번역 다듬기 1장: 바뀐 상자 1 · AI 0회(캐시 1상자)"


def test_old_prompt_answer_failing_new_rule_is_asked_again(monkeypatch):
    """운영 13:22 기록(옛 판): 21번 「부드럽고 쫄깃한 식감」 그대로 → 새 규칙(가구에 식감 금지)에 걸리니 그 상자만 다시 묻는다."""
    from src.ai import llm
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _ex()
    ex["images_ko"][0]["polish"] = {"rows": [{"id": "t0", "src": "软糯Q弹", "tgt": "부드럽고 쫄깃한 식감", "ko": "부드럽고 쫄깃한 식감",
                                             "ai": "부드럽고 쫄깃한 식감", "from": "tencent", "why": ""}], "calls": 1}
    calls = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda p, **k: calls.append(1) or {"text": json.dumps({"boxes": [{"id": "t0", "ko": "부드럽고 탄탄한 쿠션감"}]})})
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "apply", lambda *a, **k: {"ok": True, "version": "edit:1"})
    r = P.polish_entry(ex, "gallery", 0)
    assert len(calls) == 1 and r["cached"] == 0 and r["rows"][0]["ko"] == "부드럽고 탄탄한 쿠션감"


# ── 3. 상세 타일 = 갤러리처럼: 탭 → 사진 편집기 · 「사진 편집」 버튼 · 제외 타일도 · 닫으면 판정표 다시 읽기 ─────────

def test_detail_tiles_open_editor_and_plan_route():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "x", "detail_images": ["https://img/d0.jpg", "https://img/d1.jpg"],
          "detail_images_ko": [{"idx": 1, "status": "excluded", "vendor": "rule", "exclude": "판촉", "reason": "등록에서 뺍니다 — 판촉"}]}
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11l", title="x",
                   price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11l"
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert "function kgpDetailEdit(idx)" in html and "window.kgpImageEdit.open(_ITEM_ID, 'detail', idx" in html
    assert 'data-role="detail-edit"' in html and "data-role=\"detail-edit-img\"" in html and "kgpImageEdit = " in html.replace("window.kgpImageEdit = ", "kgpImageEdit = ")
    d = c.get(f"/seller/collect/{iid}/detail-plan").get_json()
    assert d["ok"] and [p["idx"] for p in d["plan"]] == [0, 1]


# ── 4. OCR 진단: 「//img…」 주소를 번역 경로처럼 고쳐 받는다(운영 상세 1 「판정 못 함(ValueError)」) ──────────────

def test_ocr_compare_fixes_scheme_less_url(monkeypatch):
    from src.services import detail_image_plan as dip
    from src.services import image_translate_tencent as tc
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as S
    u = "//img.alicdn.com/imgextra/i2/x.jpg_1200x1200q30.jpg_.webp"
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=2", seller_id="y11l2", title="x", price="1",
                   currency="CNY", extra={"detail_images": [u], "detail_images_ko": [{"idx": 0, "status": "skipped",
                                          "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로"}]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    got = []
    monkeypatch.setattr(tc, "fetch_image", lambda url: got.append(url) or (b"", "x"))
    D.run(iid)
    assert got and got[0] == dip.fix_url(u) and got[0].startswith("https://")
