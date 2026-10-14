"""Y11-E(오너 2026-10-14 17:36) — 「원본 훼손」 조사 결과와 수리.

조사(운영 읽기 전용, 값): VRSUK 4ebaf1b8 갤러리 3(나무 등판·책 더미 사진)의 수집 원본(`extra.images[3]`, alicdn)은
그대로였다 — 10-13 20:30에 떠 둔 원본 사본(`copy-…_p3_ORIGINAL.webp`)도 왼쪽 위가 빈 벽이다. 글자(「Zaha Hadid」·
「IS THAT YUO」·「Water color Painting」)는 **오른쪽 아래 거꾸로 놓인 책등**에 있다. 텐센트 이미지 번역은 그 책등을
제대로 번역해 그렸지만 줄 상자를 **180° 돌린 그림 기준**으로 돌려줬고(SDK `Angle` = 「逆时针图片角度」), 우리가 그대로
그려 상자가 빈 벽에 떴다. 그 벽을 지운 편집(08:37:26 UTC, by=user)이 오늘 2번째 편집이다.

픽스처 `y11e_vrsuk_g3_{orig,ko}.jpg` = 그 원본 사본·텐센트 번역본을 360×480으로 줄인 것(운영 Cloudinary에서 받음).
상자 5개 = 운영 `images_ko[3].boxes` 값 그대로(1440×1920 → ÷4).
"""
from __future__ import annotations

import base64
import io
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ORIG = open(os.path.join(FIX, "y11e_vrsuk_g3_orig.jpg"), "rb").read()
KO = open(os.path.join(FIX, "y11e_vrsuk_g3_ko.jpg"), "rb").read()
#: 운영 images_ko[3].boxes(1440×1920) ÷ 4 — 텐센트가 준 그대로(180° 돌린 틀)
PROD_BOXES = [
    {"x": 81, "y": 53, "w": 8, "h": 5, "src": "best arch", "tgt": "최고의 아치"},
    {"x": 38, "y": 54, "w": 36, "h": 7, "src": "Zaha Hadid", "tgt": "자하 하디드"},
    {"x": 36, "y": 62, "w": 45, "h": 6, "src": "IS THAT YUO IS THAT YUO", "tgt": "그게 유오인가? 그게 유오인가?"},
    {"x": 45, "y": 68, "w": 21, "h": 6, "src": "Wister color Painting", "tgt": "와이스터 컬러 페인팅"},
    {"x": 314, "y": 138, "w": 37, "h": 92, "src": "T", "tgt": "T"},
]
ORIG_URL = "https://img.alicdn.com/imgextra/i4/2210826600484/O1CN01ZSJvX51FRilzqFSGp_!!2210826600484.jpg"
KO_URL = "https://res.cloudinary.com/x/image/upload/v1/proxy-commerce/seller/sel-20261014-082841_4ebaf1b8_p3_TENCENT.jpg"


def _in_book(b):
    """책 더미 자리(오른쪽 아래, 360×480 기준 x 250~330 · y 395~435) 또는 왼쪽 탁자 — 빈 벽(왼쪽 위)이 아니다."""
    return b["y"] > 200


# ── 1. 상자 틀: 그림으로 잰다 ─────────────────────────────────────────────────────────────

def test_vrsuk_boxes_are_in_a_180_rotated_frame_and_land_on_the_book_spines():
    from src.services import box_frame as F
    got = F.pick(ORIG, KO, PROD_BOXES)
    assert got["frame"] == "rot180"
    assert got["scores"]["rot180"] > 2 * got["scores"]["identity"]
    by = {b["src"]: b for b in got["boxes"]}
    assert 260 <= by["Zaha Hadid"]["x"] <= 300 and 400 <= by["Zaha Hadid"]["y"] <= 430        # 오른쪽 아래 책등
    assert all(_in_book(b) for b in got["boxes"])                                             # 왼쪽 위 빈 벽엔 하나도 없다
    again = F.pick(ORIG, KO, got["boxes"])                                                     # 바로잡은 상자는 그대로 틀
    assert again["frame"] == "identity"


def test_no_visible_difference_means_boxes_are_not_shown():
    """번역 전후 차이를 어느 틀에서도 못 찾으면 「확인 못 함」 — 상자를 보여 주지 않는다(빈 벽에 상자 금지)."""
    from src.services import box_frame as F
    got = F.pick(ORIG, ORIG, PROD_BOXES)
    assert got["frame"] == "unknown" and got["boxes"] == [] and got["why"]


def test_translate_image_returns_boxes_in_original_frame(monkeypatch):
    """텐센트 응답(180° 틀 상자) → `translate_image`가 원본 좌표로 바로잡아 돌려준다 → 저장 장에 틀·번역본 주소."""
    from unittest.mock import patch
    from src.services import image_translate_tencent as tc
    from src.services import image_translate_store as istore

    class _B:
        def __init__(self, b):
            self.X, self.Y, self.Width, self.Height = b["x"], b["y"], b["w"], b["h"]

    class _D:
        def __init__(self, b):
            self.SourceLineText, self.TargetLineText, self.BoundingBox = b["src"], b["tgt"], _B(b)
            self.LineHeight = self.LinesCount = None

    class _R:
        Source, Target, Angle, RequestId = "en", "ko", 180.0, "req"
        Data = base64.b64encode(KO).decode()
        SourceText, TargetText = "Zaha Hadid", "자하 하디드"
        TransDetails = [_D(b) for b in PROD_BOXES]

    class _Cli:
        def ImageTranslateLLM(self, req):
            return _R()

    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), patch.object(tc, "fetch_image", lambda u: (ORIG, "")):
        out = tc.translate_image(url=ORIG_URL)
    assert out["ok"] and out["box_frame"] == "rot180" and out["angle_raw"] == 180.0
    assert all(_in_book(l["box"]) for l in out["lines"])
    monkeypatch.setattr(istore, "store_translated", lambda *a, **k: {"url": KO_URL, "stored_by": "cdn", "bytes": 9})
    e = istore.build_entry(3, out, item_id="4ebaf1b8", kind="gallery")
    assert e["box_frame"] == "rot180" and e["translated_url"] == KO_URL and e["boxes_img"] == KO_URL
    assert all(_in_book(b) for b in e["boxes"])


# ── 2. 옛 상자(틀 확인 전) · 그림이 바뀌면 상자 무효 ─────────────────────────────────────────

def _vrsuk_extra(edit=False):
    e = {"idx": 3, "kind": "gallery", "status": "done", "use": True, "vendor": "tencent", "url": KO_URL,
         "boxes": json.loads(json.dumps(PROD_BOXES)), "box_size": [360, 480]}
    if edit:                                            # 운영 그대로 — 빈 벽을 지운 편집본(08:37:26)
        ed_url = "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_36;y_61;w_46;h_7))/v1/proxy-commerce/edit/w.jpg"
        e.update(url=ed_url, edit={"url": ed_url, "base": KO_URL, "prev_url": KO_URL, "prev_use": True, "prev_status": "done",
                                   "by": "user", "ops": [{"id": "t2", "action": "erase"}], "credits": 0.051, "created": False,
                                   "erased": ["IS THAT YUO IS THAT YUO"], "history": []})
    return {"images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg", "https://img.alicdn.com/c.jpg", ORIG_URL],
            "images_ko": [e]}


def test_old_translated_boxes_are_checked_and_fixed_before_drawing(monkeypatch):
    from src.services import image_edit as E
    monkeypatch.setattr(E, "_fetch", lambda u: {ORIG_URL: ORIG, KO_URL: KO}.get(u, b""))
    ex = _vrsuk_extra()
    p = E.plan(ex, "gallery", 3, small=None, fetch=False)
    assert p["current"] == "translated" and len(p["boxes"]) == 5
    assert all(_in_book(b) for b in p["boxes"])                                               # 빈 벽에 상자 0
    assert ex["images_ko"][0]["box_frame"] == "rot180" and ex["images_ko"][0]["boxes_img"] == KO_URL


def test_old_boxes_that_cannot_be_checked_are_dropped_and_read_again_by_ocr(monkeypatch):
    from src.services import image_edit as E
    monkeypatch.setattr(E, "_fetch", lambda u: b"")                                            # 원본·번역본을 못 받음
    seen = []
    monkeypatch.setattr(E, "_ocr_version", lambda url: seen.append(url) or {"ok": True, "size": [360, 480],
                        "boxes": [{"x": 280, "y": 412, "w": 45, "h": 6, "src": "IS THAT YUO", "tgt": ""}]})
    ex = _vrsuk_extra()
    p = E.plan(ex, "gallery", 3, small=None, fetch=True)
    e = ex["images_ko"][0]
    assert "boxes" not in e and e["box_frame"] == "unknown" and e["boxes_dropped"]["n"] == 5
    assert seen == [KO_URL] and [b["src"] for b in p["boxes"]] == ["IS THAT YUO"] and all(_in_book(b) for b in p["boxes"])


def test_boxes_belong_to_a_version_and_a_new_image_reads_its_own(monkeypatch):
    """편집본·원본 상자는 그 그림을 OCR — 기록의 그림 주소가 지금 그림과 다르면 쓰지 않는다."""
    from src.services import image_edit as E
    monkeypatch.setattr(E, "_fetch", lambda u: {ORIG_URL: ORIG, KO_URL: KO}.get(u, b""))
    seen = []
    monkeypatch.setattr(E, "_ocr_version", lambda url: seen.append(url) or {"ok": True, "size": [360, 480], "boxes": []})
    ex = _vrsuk_extra(edit=True)
    p = E.plan(ex, "gallery", 3, small=None, fetch=True)
    assert p["current"] == "edit:1" and seen == [ex["images_ko"][0]["url"]]                    # 편집본 그림을 읽는다(번역본 상자 재사용 X)
    E.plan(ex, "gallery", 3, small=None, fetch=True)
    assert len(seen) == 1                                                                     # 같은 그림 — 저장분
    ex["images_ko"][0]["vboxes"]["edit:1"]["img"] = "https://res.cloudinary.com/x/other.jpg"  # 그림이 바뀌었다
    E.plan(ex, "gallery", 3, small=None, fetch=True)
    assert len(seen) == 2


# ── 3. 버전: 수집 원본 / 번역본 / 편집본 n · 「원본으로」 · 「되돌리기」 ─────────────────────────

def test_versions_of_the_vrsuk_photo_and_original_button_opens_the_collected_original(monkeypatch):
    from src.services import image_edit as E
    from src.services import image_translate_store as istore
    ex = _vrsuk_extra(edit=True)
    vs = E.versions(ex, "gallery", 3)
    assert [(v["key"], v["label"]) for v in vs] == [("original", "수집 원본"), ("translated", "번역본"), ("edit:1", "편집본 1")]
    assert vs[0]["url"] == ORIG_URL and vs[1]["url"] == KO_URL
    assert E.select(ex, "gallery", 3, "original")["ok"]
    plan = {p["idx"]: p for p in istore.effective_plan(ex, originals=ex["images"])}
    assert plan[3]["url"] == ORIG_URL and plan[3]["source"] == "original"                     # 나가는 사진도 수집 원본
    assert ex["images"][3] == ORIG_URL                                                         # 원본 주소는 손대지 않음
    assert E.select(ex, "gallery", 3, "edit:1")["ok"] and E.revert(ex, "gallery", 3)["back"] == "translated"
    assert [v["key"] for v in E.versions(ex, "gallery", 3)] == ["original", "translated", "edit:1"]   # 버전은 남는다


def test_select_route_and_retranslate_keeps_edit_versions(monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.services import image_edit as E
    from src.services import image_translate_store as istore
    from src.order_webhook import app
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=748639898871", seller_id="y11e",
                   title="x", price="1", currency="CNY", extra=_vrsuk_extra(edit=True))
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11e"
    r = c.post(f"/seller/collect/{iid}/image-edit/gallery/3/select", json={"key": "original"}).get_json()
    assert r["ok"] and r["current"] == "original"
    sv = json.loads(S.get(iid, seller_ids={"y11e"})["extra_json"])
    assert sv["images"][3] == ORIG_URL and E.current_key(sv["images_ko"][0]) == "original"
    assert c.post(f"/seller/collect/{iid}/image-edit/gallery/3/select", json={"key": "edit:9"}).status_code == 409
    new = {"idx": 3, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/new_TENCENT.jpg"}
    merged = istore.merge_images_ko(sv, [new])
    assert [v["key"] for v in E.versions({"images": sv["images"], "images_ko": merged}, "gallery", 3)] == \
        ["original", "translated", "edit:1"]                                                   # 다시 번역해도 편집본 1은 남는다


# ── 4. 수집 원본 불변 ─────────────────────────────────────────────────────────────────────

def test_collected_original_cannot_be_overwritten():
    from src.seller_console import collect_history_store as S
    ex = _vrsuk_extra()
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11e-a",
                   title="x", price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    sv = json.loads(S.get(iid, seller_ids={"y11e-a"})["extra_json"])
    assert sv["images_original"] == ex["images"]                                              # 수집할 때 얼려 둔다
    bad = dict(sv, images=sv["images"][:3] + [KO_URL])                                        # 번역본을 원본 자리에
    with pytest.raises(S.OriginalImageOverwrite):
        S.update(iid, seller_ids={"y11e-a"}, extra_json=json.dumps(bad))
    edited = dict(sv, images=sv["images"][:3] + ["https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_1;y_1;w_2;h_2))/v1/proxy-commerce/edit/q.jpg"])
    with pytest.raises(S.OriginalImageOverwrite):
        S.update(iid, seller_ids={"y11e-a"}, extra_json=json.dumps(edited))
    swapped = dict(sv, images_original=["https://img.alicdn.com/other.jpg"] + sv["images_original"][1:])
    with pytest.raises(S.OriginalImageOverwrite):
        S.update(iid, seller_ids={"y11e-a"}, extra_json=json.dumps(swapped))
    with pytest.raises(S.OriginalImageOverwrite):
        S.append(source="extension", url="https://detail.tmall.com/item.htm?id=2", seller_id="y11e-a", title="x",
                 price="1", currency="CNY", extra={"images": [KO_URL]})
    after = json.loads(S.get(iid, seller_ids={"y11e-a"})["extra_json"])
    assert after["images"][3] == ORIG_URL and after["images_original"] == ex["images"]       # 하나도 안 바뀌었다
    more = dict(after, images=after["images"] + ["https://img.alicdn.com/new.jpg"])            # 다시 수집으로 늘어난 원본은 뒤에 붙는다
    assert S.update(iid, seller_ids={"y11e-a"}, extra_json=json.dumps(more))
    assert json.loads(S.get(iid, seller_ids={"y11e-a"})["extra_json"])["images_original"][-1] == "https://img.alicdn.com/new.jpg"


def test_manual_photo_and_original_copy_are_not_derived():
    from src.seller_console import collect_history_store as S
    assert not S.is_derived_image("https://res.cloudinary.com/d/image/upload/v1/proxy-commerce/manual/a.jpg")
    assert not S.is_derived_image("https://res.cloudinary.com/d/image/upload/v1/proxy-commerce/seller/copy-20261013-203029_4e_p3_ORIGINAL.webp")
    assert S.is_derived_image(KO_URL) and S.is_derived_image("/seller/collect/image-ko/abc/3")


# ── 5. OCR 상자도 원본 틀로 ──────────────────────────────────────────────────────────────

def test_ocr_uses_polygon_and_drops_rotated_item_polygon_without_it(monkeypatch):
    from PIL import Image
    from src.services import ocr_tencent as O
    b = io.BytesIO()
    Image.new("RGB", (800, 800), (255, 255, 255)).save(b, "JPEG")
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: {"Angel": 180, "TextDetections": [
        {"DetectedText": "Zaha Hadid", "Confidence": 90, "ItemPolygon": {"X": 10, "Y": 10, "Width": 100, "Height": 20},
         "Polygon": [{"X": 600, "Y": 700}, {"X": 700, "Y": 700}, {"X": 700, "Y": 720}, {"X": 600, "Y": 720}]},
        {"DetectedText": "IS THAT YUO", "Confidence": 90, "ItemPolygon": {"X": 10, "Y": 40, "Width": 100, "Height": 20}}]})
    r = O.read_boxes(b.getvalue())
    assert r["angle"] == 180 and [(x["src"], x["x"], x["y"]) for x in r["boxes"]] == [("Zaha Hadid", 600, 700)]
