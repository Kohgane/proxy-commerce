"""Y11-H(오너 2026-10-14) — OCR 사전검사 한자 누락 · Y11-J5 대표 사진 상자 값 · Y11-J6 「빼고 등록」은 상자만 지운다.

재현: VRSUK 상세 3·6·7(idx 2·5·6) — 사진에 한자 문장이 큰데 「중국어 글자 없음(OCR 판정 — 한자 0)」, 읽은 글자는 라틴만
(「Disponibile Subito-Tutto tuo ora」 · 「NICEIFEELING(DITALIA®…」 · 「0TOP1TVRSUK,LOUNGE…」). 예전 사전검사는 긴 변 1024로 줄이고
LanguageType auto였다. 상세 사진은 세로로 길어(790×5000 등) 1024면 가로가 162px — 한자 획이 뭉개진다.
"""
from __future__ import annotations

import base64
import io

import pytest


def _jpeg(w=400, h=1600) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


@pytest.fixture
def ocr(monkeypatch):
    """텐센트 OCR 가짜 — 부를 때 보낸 바이트·LanguageType을 적고, 정해 둔 줄을 돌려준다."""
    from src.services import ocr_tencent as O
    calls, lines = [], {"v": []}
    monkeypatch.setenv("IMAGE_OCR_PRECHECK", "1")
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "unopened", lambda: False)

    def _call(b64):
        calls.append({"bytes": base64.b64decode(b64), "lang": getattr(O._LANG, "value", None) or "auto"})
        return {"TextDetections": [{"DetectedText": t, "Confidence": 95} for t in lines["v"]]}
    monkeypatch.setattr(O, "_call", _call)
    return calls, lines


# ── 1. 사전검사: 줄이지 않고(번역에 보내는 바이트 그대로) · 인식 언어 zh ─────────────────────────────

def test_precheck_sends_bytes_as_is_with_zh(ocr):
    from src.services import image_text_precheck as P
    calls, lines = ocr
    raw = _jpeg(790, 5000)                       # 세로로 긴 상세 사진
    lines["v"] = ["小时候的", "沙发"]
    assert P.han_text(raw) == (True, "小时候的沙发")
    assert calls[-1]["bytes"] == raw             # 풀지도 줄이지도 않음(예전: 긴 변 1024 → 가로 162px)
    assert calls[-1]["lang"] == "zh"


def test_other_paths_keep_1024_auto(ocr):
    """대표 사진 판정(아무 글자) 경로는 그대로 — 1024 · auto."""
    from PIL import Image
    from src.services import image_text_precheck as P
    calls, lines = ocr
    lines["v"] = ["INTERSTELLAR"]
    P.all_text(_jpeg(790, 5000))
    with Image.open(io.BytesIO(calls[-1]["bytes"])) as im:
        assert max(im.size) == 1024
    assert calls[-1]["lang"] == "auto"


def test_precheck_side_env_floor_is_1600(monkeypatch, ocr):
    from PIL import Image
    from src.services import image_text_precheck as P
    calls, lines = ocr
    monkeypatch.setenv("IMAGE_OCR_PRECHECK_SIDE", "1000")
    assert P.precheck_side() == 1600              # 1600 미만은 받지 않는다(오너: 하한 1600)
    lines["v"] = ["汉字"]
    P.han_text(_jpeg(790, 5000))
    with Image.open(io.BytesIO(calls[-1]["bytes"])) as im:
        assert max(im.size) == 1600


# ── 2. 「한자 0」인데 라틴 글자가 있으면 건너뛰지 않는다(번역으로) · 둘 다 없을 때만 건너뜀 ───────────────

def test_latin_only_is_unknown_and_goes_to_translation(ocr, monkeypatch):
    from src.services import image_text_precheck as P
    from src.services import image_translate_auto as A
    from src.services import image_translate_budget as B
    from src.services import image_translate_tencent as tc
    calls, lines = ocr
    lines["v"] = ["Disponibile Subito-Tutto tuo ora"]           # VRSUK 상세 3 — 실제 읽힌 글자
    assert P.han_text(_jpeg())[0] is None
    sent = []
    monkeypatch.setattr(tc, "fetch_image", lambda u: (_jpeg(), ""))
    monkeypatch.setattr(B, "can_send", lambda m: (True, 0.0, 200.0))
    monkeypatch.setattr(tc, "translate_image", lambda **k: sent.append(k) or {"ok": False, "vendor": "tencent",
                                                                           "error_code": "FailedOperation.PictureWithoutText"})
    e = A.translate_page("https://img.example/d3.jpg", idx=2, kind="detail", item_id="i", seller_id="s")
    assert len(sent) == 1                                        # 텐센트 번역에 보냈다
    assert "OCR 판정" not in str(e.get("reason") or "")


def test_no_han_and_no_latin_is_skipped(ocr):
    from src.services import image_text_precheck as P
    _calls, lines = ocr
    lines["v"] = ["2025", "-", "88"]                              # 숫자·기호만 — 글자 거의 없음
    assert P.han_text(_jpeg())[0] is False
    lines["v"] = ["VR"]                                          # 라틴 6자 미만
    assert P.han_text(_jpeg())[0] is False


# ── 3. 진단: 장마다 네 가지(1024·auto / 원본·auto / 1600·zh / 원본·zh) 한자·라틴 수 ─────────────────

def test_compare_variants_counts(ocr, monkeypatch):
    from src.services import ocr_compare_diag as D
    from src.services import ocr_tencent as O
    calls, _lines = ocr

    def _call(b64):                                              # 크게·zh로 보낼 때만 한자를 읽는 공급사 흉내
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            big = min(im.size) >= 500
        lang = getattr(O._LANG, "value", None) or "auto"
        txt = "小时候的沙发Disponibile" if (big and lang == "zh") else "Disponibile"
        calls.append(lang)
        return {"TextDetections": [{"DetectedText": txt, "Confidence": 92}]}
    monkeypatch.setattr(O, "_call", _call)
    rows = {r["name"]: r for r in D.measure_page(_jpeg(790, 5000))}
    assert list(rows) == ["1024·auto", "원본·auto", "1600·zh", "원본·zh"]
    assert rows["1024·auto"]["han"] == 0 and rows["1024·auto"]["latin"] == 11
    assert rows["원본·zh"]["han"] == 6
    assert rows["1600·zh"]["han"] == 0              # 세로로 긴 사진은 긴 변 1600도 가로 253px — 그래서 원본 크기로 보낸다
    assert calls == ["auto", "auto", "zh", "zh"]


def test_explain_boxes_names_the_missed_condition(monkeypatch):
    """Y11-J5: 대표 사진의 「소품 글자(작음) … 0.34%」 — 소품 규칙(면적<0.5% 그리고 기울기≥20°·확신<70)에 안 걸린 조건을 적는다."""
    from src.services import ocr_compare_diag as D
    from src.services import ocr_tencent as O
    W, H = 1000, 1000
    box = {"x": 10, "y": 10, "w": 68, "h": 50, "src": "이탈리아 브랜드", "conf": 78.0, "tilt": 2.0}     # 0.34%
    monkeypatch.setattr(O, "read_boxes", lambda raw: {"ok": True, "boxes": [dict(box)], "size": [W, H], "angle": 0.0})
    r = D.explain_boxes(b"x")
    b = r["boxes"][0]
    assert r["frame"] == "identity" and b["prop"] is False and b["area_pct"] == 0.34
    assert any("기울기 2.0°" in m for m in b["miss"]) and any("확신 78.0" in m for m in b["miss"])
    assert r["minor"] is True                                    # Y11-D 줄(평균 확신 < 85)은 그래서 뜬다


def test_admin_compare_page_renders_saved_result(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.order_webhook import app
    q.reset_for_tests()
    q.state_set("diag:ocr_compare", {"item": "4ebaf1b8", "pages": [{"no": 3, "url": "https://img/x.jpg", "size": [790, 5000],
                                     "variants": [{"name": "1024·auto", "ok": True, "han": 0, "latin": 28, "text": "Disponibile"}]}],
                                     "rep": {"ok": True, "angle": 0, "frame": "identity", "size": [800, 800], "boxes": [],
                                             "real_area_pct": 0.34, "real_conf_avg": 78, "minor": True, "minor_rule": "규칙"}})
    q.state_set("diag:ocr_recheck", {"count": {"total": 107, "han": 9, "send": 65, "none": 30, "unknown": 1, "fetch_fail": 2},
                                     "hits": []})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "admin"; s["user_role"] = "admin"
    html = c.get("/admin/diagnostics/ocr-compare").get_data(as_text=True)
    assert "상세 3번" in html and "790×5000" in html and "Disponibile" in html
    assert "107장 중 한자 나옴 9" in html and "라틴 있어 번역으로 65" in html
    q.reset_for_tests()


# ── 4. Y11-J6: 사람이 누른 「빼고 등록」은 그 낱말 상자만 지운다 · 자동 적용은 픽셀을 안 바꾼다 ────────────

def _ex_with_eames():
    return {"title_ko": "라운지 체어", "images": ["https://img/a.jpg"], "detail_images": [],
            "images_ko": [{"idx": 0, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/t0.jpg",
                           "translated_url": "https://res.cloudinary.com/x/t0.jpg",
                           "source_text": "Eames Chair 休闲椅", "target_text": "이임스 레이어 Eames Chair 라운지 의자"}]}


def _fake_edit(monkeypatch, boxes):
    from src.services import image_edit as IE
    applied = []
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "plan", lambda ex, kind, idx, **k: {"boxes": boxes, "why": ""})

    def _apply(ex, kind, idx, ops, by="user", small=None):
        applied.append((kind, idx, [o["id"] for o in ops], by))
        e = ex["images_ko"][idx]
        e.setdefault("edits", []).append({"n": 1, "url": "https://res.cloudinary.com/x/e1.jpg", "base_key": "translated"})
        e["url"] = "https://res.cloudinary.com/x/e1.jpg"
        return {"ok": True, "version": "edit:1", "erased": ["Eames Chair", "이임스 레이어 Eames Chair"], "pending": False}
    monkeypatch.setattr(IE, "apply", _apply)
    return applied


def test_strip_erases_only_matching_boxes(monkeypatch):
    from src.services import risk_gate as R
    applied = _fake_edit(monkeypatch, [{"id": "t0", "src": "Eames Chair", "tgt": "이임스 레이어 Eames Chair"},
                                       {"id": "t1", "src": "休闲椅", "tgt": "라운지 의자"}])
    ex = _ex_with_eames()
    h = next(x for x in R.scan(ex)["hits"] if x["label"] == "임스")
    assert R.decide(ex, h["key"], "strip", by="owner")["ok"]
    e = ex["images_ko"][0]
    assert applied == [("gallery", 0, ["t0"], "risk")]           # 낱말 든 상자만 · 편집 주체 risk
    assert not e.get("risk_exclude") and e["risk_erase"]["edit"] == 1
    assert not any(x["label"] == "임스" for x in R.scan(ex)["hits"])  # 지운 글자는 다시 안 센다
    assert R.strip_image_line(ex, h) == "사진 1장: 글자 상자만 지움 1"


def test_strip_falls_back_to_exclusion_with_reason(monkeypatch):
    from src.services import risk_gate as R
    _fake_edit(monkeypatch, [{"id": "t1", "src": "休闲椅", "tgt": "라운지 의자"}])   # 그 낱말 상자가 없다
    ex = _ex_with_eames()
    h = next(x for x in R.scan(ex)["hits"] if x["label"] == "임스")
    R.decide(ex, h["key"], "strip")
    assert "사진째 뺌(그 낱말이 든 글자 상자를 못 찾음)" in ex["images_ko"][0]["risk_exclude"]
    assert R.strip_image_line(ex, h).startswith("사진 1장: 사진째 뺌 1(그 낱말이 든 글자 상자를 못 찾음")


def test_auto_strip_never_changes_pixels(monkeypatch):
    from src.services import risk_gate as R
    applied = _fake_edit(monkeypatch, [{"id": "t0", "src": "Eames Chair", "tgt": ""}])
    ex = _ex_with_eames()
    h = next(x for x in R.scan(ex)["hits"] if x["label"] == "임스")
    R.strip_extra(ex, h)                                          # 기억된 「빼고 등록」·등록 몸통 재적용 경로
    assert applied == [] and ex["images_ko"][0]["risk_exclude"]


def test_reverting_the_erase_brings_the_hit_back(monkeypatch):
    from src.services import risk_gate as R
    _fake_edit(monkeypatch, [{"id": "t0", "src": "Eames Chair", "tgt": ""}])
    ex = _ex_with_eames()
    h = next(x for x in R.scan(ex)["hits"] if x["label"] == "임스")
    R.decide(ex, h["key"], "strip")
    ex["images_ko"][0]["url"] = ex["images_ko"][0]["translated_url"]       # 사용자가 번역본으로 되돌림
    assert R._risk_erased(ex["images_ko"][0]) == []
