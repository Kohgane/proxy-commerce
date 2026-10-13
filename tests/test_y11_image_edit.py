"""Y11(오너 2026-10-14) — 사진 편집: 글자 상자·판촉 배지를 탭해서 지우기·고치기 · 자동 1차(판촉 + 제품 영역 밖만).

재현: VRSUK 4ebaf1b8 대표사진(운영 저장값 `tests/fixtures/y10_4ebaf1b8_extra.json` images_ko[0] — 원문·번역문 글자).
⚠️ 그 장의 **글자 상자 좌표는 저장된 적이 없다**(이번부터 저장) — 여기 상자·사진은 오너 실측 07:04 배치(우상단 쿠폰 2 ·
하단 띠 3줄 · 좌상단 로고 · 가운데 의자)대로 만든 **합성**이다. Cloudinary·텐센트 호출은 흉내(편집 변환 문자열은 실제 조립).
"""
from __future__ import annotations

import io
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y10_4ebaf1b8_extra.json")

BOXES = [   # 오너 실측 배치(합성 좌표, 800×800)
    {"x": 20, "y": 20, "w": 300, "h": 40, "src": "-VRSUK Italian brand·卫斯克", "tgt": "-VRSUK 이탈리아 브랜드·웨이스커"},
    {"x": 620, "y": 20, "w": 160, "h": 90, "src": "*88VIP SALE 235 RMB 消费券", "tgt": "*88VIP 세일 235 RMB 소비 쿠폰"},
    {"x": 620, "y": 130, "w": 160, "h": 80, "src": "天猫国际加补券 320 RMB 大额加补券", "tgt": "티몰 국제 추가 쿠폰"},
    {"x": 20, "y": 700, "w": 360, "h": 40, "src": "1元抵88元+赠品|新客立减200元", "tgt": ""},
    {"x": 400, "y": 700, "w": 380, "h": 40, "src": "国庆狂欢 OFF a 55%", "tgt": ""},
    {"x": 20, "y": 750, "w": 300, "h": 40, "src": "·静享意式家", "tgt": ""},
]


def _photo(chair=(200, 180, 600, 640), coupons=True):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (800, 800), (245, 243, 240))
    d = ImageDraw.Draw(im)
    d.rectangle(list(chair), fill=(120, 80, 50))               # 의자(제품)
    if coupons:
        d.rectangle([620, 20, 780, 110], fill=(230, 40, 40))   # 쿠폰 1
        d.rectangle([620, 130, 780, 210], fill=(240, 120, 20)) # 쿠폰 2
        d.rectangle([0, 690, 800, 800], fill=(200, 30, 30))    # 하단 띠
    d.rectangle([20, 20, 320, 60], fill=(30, 30, 30))          # 로고
    small = im.copy()
    small.thumbnail((256, 256))
    return small


def _ex():
    with open(FIX, encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_doc", None)
    d["images_ko"][0].update(boxes=json.loads(json.dumps(BOXES)), box_size=[800, 800])
    return d


@pytest.fixture
def cloud(monkeypatch):
    """Cloudinary 원격 업로드 흉내 — 받은 변환 문자열을 그대로 적어 두고 eager 주소를 돌려준다."""
    from src.db import image_translate_queue_pg as q
    from src.media import image_pipeline as IP
    from src.services import image_edit as E
    q.reset_for_tests()
    calls = []

    def fake_upload(src, **kw):
        tr = (kw.get("eager") or [{}])[0].get("raw_transformation", "")
        calls.append({"src": src, "transform": tr, "folder": kw.get("folder")})
        return {"ok": True, "secure_url": f"https://res.cloudinary.com/x/edit/{len(calls)}.jpg", "public_id": "e",
                "eager": [{"secure_url": f"https://res.cloudinary.com/x/image/upload/{len(calls)}/edit.jpg"}], "keys": ["eager"]}
    monkeypatch.setattr(IP, "upload_remote", fake_upload)
    monkeypatch.setattr(E, "configured", lambda: (True, ""))
    monkeypatch.setattr(E, "_ready", lambda url: (True, 200))
    monkeypatch.setattr(E, "_load_small", lambda url: (_photo(), (800, 800)))
    yield calls
    q.reset_for_tests()


# ── 8. VRSUK: 판촉 상자 4개 자동 지움 → 「프로모션 의심」 해소 → 등록에 포함 ────────────────────────

def test_plan_classifies_boxes_and_subject():
    from src.services import image_edit as E
    ex = _ex()
    p = E.plan(ex, "gallery", 0, small=_photo())
    cls = {b["src"]: (b["cls"], b["auto"]) for b in p["boxes"] if b["id"].startswith("t")}
    assert cls["-VRSUK Italian brand·卫斯克"] == ("brand", False)              # 로고 — 남김
    assert cls["*88VIP SALE 235 RMB 消费券"] == ("promo", True)
    assert cls["天猫国际加补券 320 RMB 大额加补券"] == ("promo", True)
    assert cls["1元抵88元+赠品|新客立减200元"] == ("promo", True)
    assert cls["国庆狂欢 OFF a 55%"] == ("promo", True)
    assert cls["·静享意式家"] == ("text", False)                                # 일반 글자 — 사용자 선택
    s = p["subject"]
    assert 190 <= s["x"] <= 210 and 170 <= s["y"] <= 190 and 590 <= s["x"] + s["w"] <= 615   # 의자 상자
    assert not [b for b in p["boxes"] if b["id"].startswith("c")]               # 쿠폰 색 배지는 글자 상자와 같은 자리 — 하나만


def test_vrsuk_auto_erases_four_promo_boxes_and_photo_goes_back_in(cloud):
    from src.services import image_edit as E
    from src.services import image_translate_store as S
    ex = _ex()
    before = S.effective_images(ex, kind="gallery")
    assert S.promo_excluded(ex["images_ko"][0]) and len(before) == 4               # 1번 사진은 「프로모션 의심」으로 빠져 있었다
    res = E.auto_promo(ex)
    assert res == [{"kind": "gallery", "idx": 0, "url": "https://res.cloudinary.com/x/image/upload/1/edit.jpg",
                    "erased_n": 4, "credits": 0.051, "error": ""}]
    tr = cloud[0]["transform"]
    assert tr.startswith("e_gen_remove:region_(") and tr.count("(x_") == 4 and "l_text" not in tr
    assert cloud[0]["src"] == "https://res.cloudinary.com/x/p0_TENCENT.jpg"    # 지금 나가는 번역본을 바탕으로(원본 보존)
    e = ex["images_ko"][0]
    assert e["edit"]["by"] == "auto" and e["url"].endswith("/1/edit.jpg") and e["edit"]["prev_url"].endswith("p0_TENCENT.jpg")
    assert S.promo_of(e) == [] and not S.promo_excluded(e)                     # 「프로모션 의심」 해소
    after = S.effective_images(ex, kind="gallery")
    assert len(after) == 5 and after[0].endswith("/1/edit.jpg")                # 편집본이 등록에 들어간다(나갈 사진)


def test_photo_without_text_boxes_is_unchanged(cloud):
    from src.services import image_edit as E
    ex = _ex()
    for e in ex["images_ko"]:
        e.pop("boxes", None)
        e.pop("box_size", None)
    ex["images_ko"] = [e for e in ex["images_ko"] if e["idx"] != 0]             # 판촉 글자 없는 장들만
    snap = json.dumps(ex, sort_keys=True)
    assert E.auto_promo(ex) == [] and cloud == []
    assert json.dumps(ex, sort_keys=True) == snap


def test_promo_box_overlapping_product_is_left_to_the_user(cloud):
    """오너(2026-10-14): 자동 지우기는 상자가 제품 영역 **밖**일 때만 — 겹치면 사용자 선택."""
    from src.services import image_edit as E
    ex = _ex()
    ex["images_ko"][0]["boxes"] = [dict(BOXES[1], x=300, y=300)]               # 쿠폰 글자가 의자 위에(색 배지 없는 사진)
    res = E.auto_promo(ex, small_loader=lambda u: _photo(coupons=False))
    assert res == [{"kind": "gallery", "idx": 0, "skipped": "제품과 겹치는 판촉 상자뿐 — 사용자 선택"}] and cloud == []
    p = E.plan(ex, "gallery", 0, small=_photo(coupons=False))
    b = next(b for b in p["boxes"] if b["id"] == "t0")
    assert b["cls"] == "promo" and b["in_subject"] and not b["auto"]


# ── 4·5. 글자 고치기 · 되돌리기 ───────────────────────────────────────────────────────────────

def test_fix_text_erases_then_overlays_noto_sans_kr(cloud):
    from src.services import image_edit as E
    ex = _ex()
    r = E.apply(ex, "gallery", 0, [{"id": "t5", "action": "text", "text": "이탈리아 감성 홈"}], small=_photo())
    assert r["ok"] and r["credits"] == 0.052                                   # gen_remove 50 + 기본 1 + 글자 1
    tr = cloud[0]["transform"]
    assert tr.startswith("e_gen_remove:region_((x_20;y_750;w_300;h_40))/")
    assert "l_text:Noto%20Sans%20KR_" in tr and "co_rgb:" in tr and "fl_layer_apply,g_north_west,x_20,y_" in tr
    assert ex["images_ko"][0]["edit"]["by"] == "user"


def test_second_edit_rebuilds_from_base_and_revert_restores(cloud):
    from src.services import image_edit as E
    from src.services import image_translate_store as S
    ex = _ex()
    E.apply(ex, "gallery", 0, [{"id": "t1", "action": "erase"}], small=_photo())
    E.apply(ex, "gallery", 0, [{"id": "t2", "action": "erase"}], small=_photo())
    assert cloud[1]["src"] == cloud[0]["src"]                                  # 편집은 매번 바탕에서(겹쳐 굽지 않는다)
    assert cloud[1]["transform"].count("(x_") == 2                             # 앞 편집 + 이번 편집
    assert ex["images_ko"][0]["edit"]["credits"] == 0.102
    assert E.revert(ex, "gallery", 0)["ok"]
    e = ex["images_ko"][0]
    assert "edit" not in e and e["url"].endswith("p0_TENCENT.jpg") and S.promo_excluded(e)


def test_daily_cap(cloud, monkeypatch):
    from src.services import image_edit as E
    monkeypatch.setenv("IMAGE_EDIT_DAILY_CAP", "1")
    ex = _ex()
    assert E.apply(ex, "gallery", 0, [{"id": "t1", "action": "erase"}], small=_photo())["ok"]
    r = E.apply(ex, "gallery", 0, [{"id": "t2", "action": "erase"}], small=_photo())
    assert not r["ok"] and "한도(1회)" in r["error"] and len(cloud) == 1


def test_trademark_box_erase_clears_risk_hit(cloud):
    """상표 위험 상자(Y10)를 지우면 그 사진의 위험 항목이 풀린다(지운 글자는 검사에서 빠진다)."""
    from src.services import image_edit as E
    from src.services import risk_gate as R
    ex = _ex()
    e = ex["images_ko"][2]                                                     # 「Zaha Hadid」 사진(3번)
    e.update(boxes=[{"x": 40, "y": 40, "w": 200, "h": 40, "src": "Zaha Hadid", "tgt": "자하 하디드"}], box_size=[800, 800])
    assert "사진 3" in R.where_line(next(h for h in R.scan(ex)["hits"] if h["label"] == "자하 하디드"))
    p = E.plan(ex, "gallery", 2, small=_photo())
    assert p["boxes"][0]["cls"] == "risk"
    E.apply(ex, "gallery", 2, [{"id": "t0", "action": "erase"}], small=_photo())
    zh = next(h for h in R.scan(ex)["hits"] if h["label"] == "자하 하디드")
    assert [i["name"] for i in zh["images"]] == ["사진 4"]                     # 3번은 풀리고 4번만 남는다


# ── 1. 상자 저장 · 옛 장은 OCR로 다시 읽기 ───────────────────────────────────────────────────

def test_translate_result_keeps_boxes_now():
    import base64
    from PIL import Image
    from src.services.image_translate_store import text_geometry
    b = io.BytesIO()
    Image.new("RGB", (750, 1000), (255, 255, 255)).save(b, "JPEG")
    g = text_geometry({"image_b64": base64.b64encode(b.getvalue()).decode(),
                       "lines": [{"source": "88VIP", "target": "88VIP", "box": {"x": 10, "y": 20, "w": 100, "h": 30}}]})
    assert g["box_size"] == [750, 1000] and g["boxes"] == [{"x": 10, "y": 20, "w": 100, "h": 30, "src": "88VIP", "tgt": "88VIP"}]


def test_ocr_boxes_are_scaled_back_to_original(monkeypatch):
    from PIL import Image
    from src.services import ocr_tencent as O
    b = io.BytesIO()
    Image.new("RGB", (2048, 2048), (255, 255, 255)).save(b, "JPEG")
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: {"TextDetections": [
        {"DetectedText": "满300减50", "Confidence": 99, "ItemPolygon": {"X": 10, "Y": 20, "Width": 100, "Height": 30}},
        {"DetectedText": "흐림", "Confidence": 20, "ItemPolygon": {"X": 1, "Y": 1, "Width": 1, "Height": 1}}]})
    r = O.read_boxes(b.getvalue())
    assert r["ok"] and r["size"] == [2048, 2048]
    assert r["boxes"] == [{"x": 20, "y": 40, "w": 200, "h": 60, "src": "满300减50", "tgt": ""}]   # 1024로 보냈다 → ×2


def test_old_entry_reads_boxes_once_via_route(cloud, monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.services import ocr_tencent as O
    from src.order_webhook import app
    import requests
    ex = _ex()
    ex["images_ko"][0].pop("boxes")
    ex["images_ko"][0].pop("box_size")
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11", title="x",
                   price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    seen = []
    monkeypatch.setattr(requests, "get", lambda url, **k: type("R", (), {"status_code": 200, "content": b"jpg"})())
    monkeypatch.setattr(O, "read_boxes", lambda raw: seen.append(raw) or {"ok": True, "boxes": BOXES[1:3], "size": [800, 800]})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11"
    d = c.get(f"/seller/collect/{iid}/image-edit/gallery/0").get_json()
    assert d["ok"] and [b["cls"] for b in d["boxes"] if b["id"].startswith("t")] == ["promo", "promo"] and len(seen) == 1
    d2 = c.get(f"/seller/collect/{iid}/image-edit/gallery/0").get_json()
    assert len(seen) == 1 and len(d2["boxes"]) == len(d["boxes"])             # 저장됨 — 다시 안 부른다
    r = c.post(f"/seller/collect/{iid}/image-edit/gallery/0", json={"ops": [{"id": "t0", "action": "erase"}]}).get_json()
    assert r["ok"] and r["credits"] == 0.051 and r["plan"]["edit"]["url"].endswith("edit.jpg")
    assert len(r["plan"]["boxes"]) == len(d["boxes"]) and len(seen) == 1     # 적용 뒤에도 상자 그대로(캡처에서 잡힌 회귀) · OCR 다시 안 부름
    assert c.post(f"/seller/collect/{iid}/image-edit/gallery/0/revert", json={}).get_json()["ok"]


def test_color_badge_outside_product_is_auto_erased_even_without_text(cloud):
    """글자를 못 읽은 쿠폰 스티커(색 덩어리)도 제품 밖이면 판촉 배지로 자동 지운다."""
    from src.services import image_edit as E
    ex = _ex()
    ex["images_ko"][0]["boxes"] = [BOXES[0]]                                   # 로고 글자만 읽힘
    p = E.plan(ex, "gallery", 0, small=_photo())
    badges = [b for b in p["boxes"] if b["id"].startswith("c")]
    assert len(badges) == 2 and all(b["cls_label"] == "판촉 배지" and b["auto"] for b in badges)


def test_old_picture_without_text_entry_is_not_a_failure_badge(monkeypatch):
    """캡처에서 잡힘 — 예전에 「실패」로 저장된 글자 없는 사진(PictureWithoutText)이 카드에 빨간 「이미지 번역 실패」로 떴다."""
    from src.services import image_translate_auto as A
    monkeypatch.setattr(A, "status", lambda item_id: {})
    ex = {"images_ko": [{"idx": 4, "status": "failed", "error_code": "UnsupportedOperation.PictureWithoutText",
                         "error_message": "翻译失败，输入为无文本图片。"}]}
    assert A.item_failure("x", ex) == {}
    ex["images_ko"].append({"idx": 5, "status": "failed", "error_code": "FailedOperation.Timeout", "error_message": "timeout"})
    assert A.item_failure("x", ex)["failed"] == 1
