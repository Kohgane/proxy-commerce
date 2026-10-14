"""Y11-G(오너 2026-10-14) — 소품 글자는 글자가 아니다 · 만드는 중 편집본 칩 · ImageNoText = 글자 없음.

규칙: 상자 하나가 소품 = 면적 < 0.5% 그리고 (기울기 ≥ 20° 또는 OCR 확신 < 70 또는 사진 전체가 180°·90° 돌린 틀).
돌린 틀(글자가 거꾸로)이면 그 사진 상자 전부 소품. 반례: 책·포스터·간판·문구 상품이면 규칙을 끈다.
⚠️ 「번역본 픽셀 차이가 상자 밖으로 안 번짐」은 운영 실측에서 쿠팡·책등이 안 갈려(둘레 차이 쿠폰 2.6~28.9 · 책등 13.3~38.1) 넣지 않았다.
"""
from __future__ import annotations

import io
import json

import pytest


def _jpeg(w=800, h=800):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(b, "JPEG")
    return b.getvalue()


# ── 판정 ─────────────────────────────────────────────────────────────────────────────────

def test_prop_rule_area_and_tilt_or_conf_or_rotated_frame():
    from src.services import prop_text as P
    S = [1000, 1000]                                                       # 0.5% = 5,000px²
    small = {"x": 0, "y": 0, "w": 60, "h": 20, "src": "OUIY TAHT"}          # 0.12%
    assert not P.is_prop(dict(small), S)                                    # 작기만 하고 또렷·반듯 — 소품 아님
    assert P.is_prop(dict(small, conf=62.0), S) and P.is_prop(dict(small, tilt=178.0), S) and P.is_prop(dict(small, tilt=25.0), S)
    assert not P.is_prop(dict(small, conf=92.0, tilt=3.0), S)
    big = {"x": 0, "y": 0, "w": 200, "h": 40, "src": "满300减50", "conf": 40.0}   # 0.8%
    assert not P.is_prop(big, S)
    assert P.is_prop(big, S, frame="rot180")                                # 사진이 통째 돌아감 = 전부 소품
    assert not P.is_prop(dict(small, src="www.tmall.com", conf=55.0), S)    # 워터마크 낱말 — 진짜 반려 사유(Y11-D 반례)
    assert P.is_prop(dict(small, src="Zaha Hadid", conf=55.0), S)           # 상표 토큰은 소품이면 소품(위험 목록 「참고」)
    pts = [{"X": 300, "Y": 120}, {"X": 100, "Y": 118}, {"X": 100, "Y": 100}, {"X": 300, "Y": 102}]
    assert P.tilt_of(pts) > 170                                             # 거꾸로 놓인 글자의 첫 변


@pytest.mark.parametrize("title,on", [("이탈리아 건축 디자인 도서", True), ("빈티지 포스터 액자 A3", True),
                                      ("가게 입간판 LED 사인보드", True), ("원목 책상 1200", False),
                                      ("노트북 거치대 알루미늄", False), ("가죽 리클라이너 의자", False)])
def test_category_counterexample_turns_the_rule_off(title, on):
    from src.services import prop_text as P
    assert P.exempt({"title_ko": title}) is on
    assert P.exempt({"category_code": "OFC", "title_ko": "볼펜"}) is True


# ── 6. ImageNoText = 글자 없음(코드 원문 안 보임) ──────────────────────────────────────────

def test_image_no_text_is_no_text_not_failure(monkeypatch):
    from src.services import ocr_tencent as O

    class _NoText(Exception):
        code = "FailedOperation.ImageNoText"
        message = "图片中未检测到文本"
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: (_ for _ in ()).throw(_NoText()))
    r = O.read_boxes(_jpeg())
    assert r["ok"] and r["boxes"] == [] and not r.get("why")
    t = O.read(_jpeg())
    assert t["ok"] and t["lines"] == [] and t["text"] == ""
    assert O._fail_why(_NoText()) == "글자 없음(OCR)" and "ImageNoText" not in O._fail_why(_NoText())


# ── 1. 대표사진 판정: 소품뿐이면 줄 없음 ───────────────────────────────────────────────────

def test_rep_photo_upside_down_ocr_means_all_prop(monkeypatch):
    from src.services import coupang_image_check as C
    from src.services import image_text_precheck as P
    from src.services import ocr_tencent as O
    monkeypatch.setattr(P, "all_text", lambda raw: (True, "满300减50"))
    monkeypatch.setattr(O, "read_boxes", lambda raw: {"ok": True, "size": [800, 800], "angle": 179.6,
                                                     "boxes": [{"x": 10, "y": 10, "w": 400, "h": 80, "src": "满300减50", "conf": 99.0}]})
    r = C.check_bytes(_jpeg())
    assert r["prop_only"] and not [f for f in r["flags"] if f["key"] in ("text", "text_small")]


# ── 2. 번역: 상자가 전부 소품이면 원본 · 일부만 소품이면 그 상자만 표시 ───────────────────────

def test_mixed_translation_keeps_real_boxes_and_marks_props(monkeypatch):
    from src.services import image_translate_store as S
    monkeypatch.setattr(S, "store_translated", lambda *a, **k: {"url": "https://res.cloudinary.com/x/t.jpg", "stored_by": "cdn", "bytes": 9})
    import base64
    res = {"ok": True, "image_b64": base64.b64encode(_jpeg()).decode(), "source_text": "满300减50 书", "target_text": "300 이상 50 할인",
           "box_frame": "identity", "prop_all": False,
           "lines": [{"source": "满300减50", "target": "300 이상 50 할인", "box": {"x": 10, "y": 10, "w": 400, "h": 80}},
                     {"source": "书", "target": "책", "box": {"x": 700, "y": 700, "w": 20, "h": 20}, "prop": True}]}
    e = S.build_entry(0, res, item_id="i", kind="gallery")
    assert e["status"] == "done" and [b.get("prop", False) for b in e["boxes"]] == [False, True]


def test_retry_does_not_resend_prop_only_photo_unless_product_is_a_book():
    from src.services import image_translate_auto as A
    ex = {"images": ["https://img.alicdn.com/a.jpg"], "title_ko": "가죽 리클라이너 의자",
          "images_ko": [{"idx": 0, "status": "skipped", "vendor": "tencent", "prop_only": True,
                         "reason": "소품 글자뿐(책등·표지·포장 등) — 원본 그대로"}]}
    p = A.translate_plan(ex, retry=True)
    assert p["send"] == [] and p["skip"]["prop"] == [("gallery", 0)]
    assert A.plan_line(p, 0) == "접수 0장 · 건너뜀 1장(소품 글자뿐 1) · 글자 없음 0장"
    ex["title_ko"] = "건축 디자인 도서"
    assert A.translate_plan(ex, retry=True)["send"] == [("gallery", 0, "ocr_skip")]


# ── 3. 편집 화면: 소품 상자는 숨김 · 적용 대상 아님 ─────────────────────────────────────────

def test_editor_hides_prop_boxes_and_never_applies_them(monkeypatch):
    from src.services import image_edit as E
    ex = {"images": ["https://img.alicdn.com/a.jpg"], "title_ko": "가죽 리클라이너",
          "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "use": True, "url": "https://res.cloudinary.com/x/t.jpg",
                         "translated_url": "https://res.cloudinary.com/x/t.jpg", "box_size": [800, 800], "box_frame": "identity",
                         "boxes": [{"x": 10, "y": 10, "w": 400, "h": 80, "src": "满300减50", "tgt": "300 이상 50 할인"},
                                   {"x": 700, "y": 700, "w": 20, "h": 20, "src": "书", "tgt": "책", "prop": True}]}]}
    p = E.plan(ex, "gallery", 0, small=None, fetch=False)
    assert [b["id"] for b in p["boxes"]] == ["t0"] and [b["id"] for b in p["prop_boxes"]] == ["p1"]
    monkeypatch.setattr(E, "configured", lambda: (True, ""))
    r = E.apply(ex, "gallery", 0, [{"id": "p1", "action": "erase"}], small=None)
    assert not r["ok"] and "탭해서" in r["error"]                            # 소품 상자는 적용 대상이 아니다


# ── 4. 위험 목록: 소품의 상표 = 「참고」 한 줄 ────────────────────────────────────────────────

def test_trademark_on_prop_is_only_a_note_vrsuk_gallery4():
    from src.services import risk_gate as R
    ex = {"title_ko": "VRSUK 비즈니스 시리즈 심플 리클라이너", "images": ["a", "b", "c", "d"],
          "images_ko": [{"idx": 3, "status": "done", "box_frame": "rot180", "url": "https://res.cloudinary.com/x/p3_TENCENT.jpg",
                         "source_text": "best arch Zaha Hadid IS THAT YUO", "target_text": "최고의 아치 자하 하디드 그게 유오인가?"}]}
    sc = R.scan(ex)
    assert not [h for h in sc["hits"] if "Zaha" in " ".join(h["found"]) or h["label"] == "자하 하디드"]
    assert "참고: 소품(사진 4)에 'Zaha Hadid'" in R.card(sc)["notes"]
    ex["title_ko"] = "자하 하디드 건축 도서"                                    # 반례: 책 상품이면 소품 규칙 끔 → 다시 위험
    assert [h for h in R.scan(ex)["hits"] if h["label"] == "자하 하디드"]


# ── 5. 만드는 중 편집본 ─────────────────────────────────────────────────────────────────

@pytest.fixture
def cloud(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.media import image_pipeline as IP
    from src.services import image_edit as E
    q.reset_for_tests()
    monkeypatch.setattr(IP, "upload_remote", lambda src, **kw: {"ok": True, "eager": [
        {"secure_url": "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_1;y_1;w_2;h_2))/v2/edit.jpg"}]})
    monkeypatch.setattr(E, "configured", lambda: (True, ""))
    monkeypatch.setattr(E, "_load_small", lambda url: (None, (800, 800)))
    yield
    q.reset_for_tests()


def _ex1():
    return {"images": ["https://img.alicdn.com/a.jpg"], "title_ko": "가죽 리클라이너",
            "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "use": True, "url": "https://res.cloudinary.com/x/t.jpg",
                           "translated_url": "https://res.cloudinary.com/x/t.jpg", "box_size": [800, 800], "box_frame": "identity",
                           "boxes": [{"x": 10, "y": 10, "w": 400, "h": 80, "src": "满300减50", "tgt": "300 이상 50 할인"}]}]}


def test_edit_still_generating_is_not_selected_and_turns_on_when_ready(cloud, monkeypatch):
    """오너 19:16: 「편집본 2」 칩 → 빈 칸 + 깨진 그림 + 「이미지 바이트 없음」. 원인: Cloudinary gen_remove는 비동기 —
    파생본이 423(만드는 중)인 채로 저장하고 그 버전을 바로 골랐다. 이제 만드는 중이면 고르지 않고 전 버전을 보이고, 다 되면 켠다."""
    from src.services import image_edit as E
    monkeypatch.setattr(E, "_ready", lambda url: (False, 423))
    ex = _ex1()
    r = E.apply(ex, "gallery", 0, [{"id": "t0", "action": "erase"}], small=None)
    assert r["ok"] and r["pending"] and E.current_key(ex["images_ko"][0]) == "translated"   # 전 버전이 그대로 나간다
    v = {x["key"]: x for x in E.versions(ex, "gallery", 0)}
    assert v["edit:1"]["ready"] is False
    s = E.select(ex, "gallery", 0, "edit:1")
    assert not s["ok"] and s["pending"] and "만드는 중" in s["error"]
    monkeypatch.setattr(E, "_head_ok", lambda url: False)
    assert not E.refresh_pending(ex, "gallery", 0) and E.current_key(ex["images_ko"][0]) == "translated"
    monkeypatch.setattr(E, "_head_ok", lambda url: True)                    # 다 됐다(200)
    assert E.refresh_pending(ex, "gallery", 0)
    assert E.current_key(ex["images_ko"][0]) == "edit:1" and E.versions(ex, "gallery", 0)[-1]["ready"] is True


def test_old_record_whose_current_edit_is_not_ready_shows_previous_version(cloud, monkeypatch):
    """운영 VRSUK 갤러리 3 기록 모양 — 편집본 2(ready=false · 423)가 지금 버전으로 저장돼 있던 경우: 열면 바탕(편집본 1)을 보인다."""
    from src.services import image_edit as E
    ex = _ex1()
    e = ex["images_ko"][0]
    e1 = "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_1;y_1;w_2;h_2))/v1/edit1.jpg"
    e2 = "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_3;y_3;w_2;h_2))/v1/edit2.jpg"
    e.update(url=e2, edits=[{"n": 1, "url": e1, "base_key": "translated", "ready": True},
                            {"n": 2, "url": e2, "base_key": "edit:1", "ready": False, "http_status": 423}])
    monkeypatch.setattr(E, "_head_ok", lambda url: False)
    assert E.refresh_pending(ex, "gallery", 0)
    assert E.current_key(e) == "edit:1" and e["url"] == e1 and e["pending_select"] == "edit:2"
    monkeypatch.setattr(E, "_head_ok", lambda url: True)
    E.refresh_pending(ex, "gallery", 0)
    assert E.current_key(e) == "edit:2"
