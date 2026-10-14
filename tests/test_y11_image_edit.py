"""Y11 · Y11-B(오너 2026-10-14) — 사진 편집: 글자 상자를 탭해서 지우기·고치기. Y11-B: 색 덩어리 검출 폐기 · 번역 우선 ·
탭한 상자만 · 자동 지우기 기본 꺼짐 · 지울 영역 = 상자 + 높이 10% · OCR 미개통 사람 말 · 갤러리 번역 입력 정규화.

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
    for e in d["images_ko"]:
        e["box_frame"] = "identity"            # Y11-E: 새 모양 — 번역할 때 원본↔번역본 차이로 좌표 틀을 확인한 상자
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
    # Y11-E: 편집본·원본 버전의 상자는 그 그림을 OCR로 읽는다 — 흉내(같은 배치)
    monkeypatch.setattr(E, "_ocr_version", lambda url: {"ok": True, "boxes": json.loads(json.dumps(BOXES)), "size": [800, 800]})
    yield calls
    q.reset_for_tests()


# ── Y11-B(오너 2026-10-14 실측): 색 덩어리 폐기 · 번역 우선 · 탭한 상자만 · 자동 꺼짐 · 지울 영역 여유 10% ──────────

def _chair_photo(full=False):
    """오너 실측 VRSUK 대표사진 모양 — 오일 왁스 가죽(주황·갈색 고채도) 의자. `full`이면 의자가 사진을 꽉 채운다."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (800, 800), (245, 243, 240))
    d = ImageDraw.Draw(im)
    if full:
        d.rectangle([0, 0, 800, 800], fill=(196, 92, 34))
    else:
        d.rectangle([240, 300, 652, 520], fill=(196, 92, 34))      # 등받이(주황 가죽)
        d.rectangle([120, 520, 757, 720], fill=(176, 80, 30))      # 좌판
    small = im.copy()
    small.thumbnail((256, 256))
    return small


def test_color_blob_detector_is_gone_and_leather_chair_is_not_a_badge(cloud):
    """실측 14:49: 색 덩어리 검출기가 의자 등받이·좌판(주황 가죽)을 「판촉 배지」로 잡아 지웠다 → 검출기 자체를 없앤다."""
    from src.services import image_edit as E
    assert not hasattr(E, "color_badges")
    ex = _ex()
    ex["images_ko"][1].update(boxes=[], box_size=[800, 800])               # 실측: 그 장의 글자 상자 0개
    p = E.plan(ex, "gallery", 1, small=_chair_photo())
    assert p["boxes"] == [] and p["why"] == E.NO_TEXT_WHY == "이 사진에서 글자를 못 찾았어요 — 지울 것이 없어요"
    r = E.apply(ex, "gallery", 1, [{"id": "c0", "action": "erase"}, {"id": "c1", "action": "erase"}], small=_chair_photo())
    assert not r["ok"] and cloud == []                                       # 옛 c# 상자는 받지 않는다 · 한도도 안 센다
    from src.services.image_edit import today_count
    assert today_count() == 0


def test_promo_photo_default_is_translated_and_only_tapped_box_is_erased(cloud):
    """판촉 글자 사진 → 기본은 번역본 그대로(아무것도 안 골라 둠) · 사용자가 탭한 상자 하나만 지운다."""
    from src.services import image_edit as E
    ex = _ex()
    p = E.plan(ex, "gallery", 0, small=_photo())
    assert p["url"].endswith("p0_TENCENT.jpg") and len(p["boxes"]) == 6        # 번역본 위에서 분류
    assert not any("auto" in b for b in p["boxes"]) and "subject" not in p     # Y11-E: 자동 지우기·제품 영역 판정 자체가 없다
    cls = {b["src"]: b["cls"] for b in p["boxes"]}
    assert cls["*88VIP SALE 235 RMB 消费券"] == "promo" and cls["-VRSUK Italian brand·卫斯克"] == "brand"
    assert cloud == []
    r = E.apply(ex, "gallery", 0, [{"id": "t1", "action": "erase"}], small=_photo())
    assert r["ok"] and len(cloud) == 1 and cloud[0]["src"].endswith("p0_TENCENT.jpg")
    tr = cloud[0]["transform"]
    assert tr == "e_gen_remove:region_((x_611;y_11;w_178;h_108))"               # 그 상자 하나 + 여유(높이 90의 10% = 9, 사방)
    assert ex["images_ko"][0]["edit"]["ops"] == [{"id": "t1", "action": "erase"}]


def test_erase_region_is_box_plus_ten_percent_of_height_only():
    from src.services import image_edit as E
    assert E.erase_rect({"x": 20, "y": 700, "w": 360, "h": 40}, [800, 800]) == {"x": 16, "y": 696, "w": 368, "h": 48}
    assert E.erase_rect({"x": 0, "y": 0, "w": 50, "h": 100}, [800, 800]) == {"x": 0, "y": 0, "w": 60, "h": 110}
    assert E.erase_rect({"x": 760, "y": 780, "w": 40, "h": 20}, [800, 800]) == {"x": 758, "y": 778, "w": 42, "h": 22}
    p = E.plan(_ex(), "gallery", 0, small=_photo())
    for b in p["boxes"]:                                                       # 화면이 빨갛게 보여 줄 영역 = 실제로 보내는 영역
        assert b["er"] == E.erase_rect({k: b[k] for k in ("x", "y", "w", "h")}, p["size"])


def test_no_automatic_pixel_change_anywhere_even_with_old_env(cloud, monkeypatch):
    """Y11-E(오너 2026-10-14): 자동 픽셀 변경 전면 금지 — `IMAGE_EDIT_AUTO` 변수·코드 삭제. 예전 변수를 켜 둬도 사전검증이 아무것도 안 지운다."""
    from src.services import image_edit as E
    from src.seller_console import collect_history_store as S
    from src.seller_console import views as V
    from src.order_webhook import app
    for gone in ("auto_promo", "auto_enabled", "subject_bbox", "ENV_AUTO"):
        assert not hasattr(E, gone)
    monkeypatch.setenv("IMAGE_EDIT_AUTO", "1")
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11e-auto", title="x",
                   price="1", currency="CNY", extra=_ex())
    iid = iid[0] if isinstance(iid, tuple) else iid
    with app.test_request_context():
        from flask import session
        session["user_id"] = "y11e-auto"
        V._pv_auto_image_edit("job-x", {"item_id": iid})
    sv = json.loads(S.get(iid, seller_ids={"y11e-auto"})["extra_json"])
    assert cloud == [] and not any(E.edits(e) for e in sv["images_ko"])


def test_untranslated_photo_asks_to_translate_first_and_ocr_unopened_is_spoken_plainly(monkeypatch):
    """순서: 번역이 먼저 — 번역 전 장은 「번역하고 글자 상자 받기」. OCR 미개통(UnOpenError)은 사람 말로, 한 시간 동안 다시 안 부름."""
    from src.services import image_edit as E
    from src.services import ocr_tencent as O
    ex = _ex()
    ex["images_ko"] = [e for e in ex["images_ko"] if e["idx"] != 1]
    p = E.plan(ex, "gallery", 1, small=_photo())
    assert p["need_translate"] and p["boxes"] == [] and "번역이 먼저" in p["why"]
    for e in ex["images_ko"]:
        e.pop("boxes", None)
        e.pop("box_size", None)

    class _Unopen(Exception):
        code = "FailedOperation.UnOpenError"
        message = "服务未开通"
    calls = []
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: calls.append(1) or (_ for _ in ()).throw(_Unopen()))
    monkeypatch.setattr(O, "_UNOPEN_AT", [0.0])
    import requests
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 255, 255)).save(buf, "JPEG")
    monkeypatch.setattr(requests, "get", lambda url, **k: type("R", (), {"status_code": 200, "content": buf.getvalue()})())
    p = E.plan(ex, "gallery", 0, small=_photo())                              # 번역은 됐지만 상자 없는 옛 장 → OCR → 미개통
    assert p["need_translate"] and p["boxes"] == []
    assert "OCR) 서비스가 텐센트 계정에 아직 개통되지 않았어요" in p["why"] and "文字识别" in p["why"]
    assert len(calls) == 1 and O.unopened()
    E.plan(ex, "gallery", 2, small=_photo())
    assert len(calls) == 1                                                     # 미개통이면 다시 부르지 않는다
    assert O.read(buf.getvalue())["why"] == O.UNOPEN_WHY and len(calls) == 1


def test_translate_route_queues_this_photo_only(monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.services import image_translate_job as job
    from src.services import image_translate_tencent as tc
    from src.order_webhook import app
    ex = _ex()
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11b", title="x",
                   price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    seen = []
    monkeypatch.setattr(tc, "is_configured", lambda: True)
    monkeypatch.setattr(job, "accept", lambda item_id, sid, idx, seller_ids=None: seen.append((item_id, list(idx))) or {"ok": True})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11b"
    r = c.post(f"/seller/collect/{iid}/image-edit/gallery/3/translate", json={})
    assert r.status_code == 202 and r.get_json()["queued"] and seen == [(iid, [3])]


def test_legacy_color_blob_edit_is_reverted_on_open(cloud):
    """운영 실측(VRSUK 사진 2): c0~c2(의자 등받이·좌판)를 지운 편집본이 「나갈 사진」이 돼 있었다 → 열면 번역본으로 되돌린다."""
    from src.seller_console import collect_history_store as S
    from src.order_webhook import app
    ex = _ex()
    e = ex["images_ko"][1]
    base = e["url"]
    e.update(url="https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_240;y_735;w_412;h_195))/v1/edit.jpg",
             edit={"base": base, "prev_url": base, "prev_use": True, "prev_status": "done", "by": "user", "credits": 0.051,
                   "ops": [{"id": "c0", "action": "erase"}, {"id": "c1", "action": "erase"}], "history": []})
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11c", title="x",
                   price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11c"
    d = c.get(f"/seller/collect/{iid}/coupang-exposure").get_json()
    assert d.get("edit_reverted") == [{"kind": "gallery", "idx": 1}]
    sv = json.loads(S.get(iid, seller_ids={"y11c"})["extra_json"])
    e1 = next(x for x in sv["images_ko"] if x["idx"] == 1)
    assert e1["url"] == base and "edit" not in e1 and sv["image_edit_reverted"][0]["idx"] == 1
    assert "edit_reverted" not in c.get(f"/seller/collect/{iid}/coupang-exposure").get_json()   # 한 번만


def test_boxes_in_sent_space_are_scaled_to_a_bigger_base(cloud, monkeypatch):
    """상자는 공급사에 보낸 그림(긴 변 ≤ 4096) 기준 — 바탕이 더 크면 그 비율로 키워 보낸다(빗나가 제품을 지우지 않게)."""
    from src.media import image_pipeline as IP
    from src.services import image_edit as E
    monkeypatch.setattr(IP, "remote_max_side", lambda: 10000)
    monkeypatch.setattr(E, "_load_small", lambda url: (_photo(), (1600, 1600)))
    ex = _ex()
    r = E.apply(ex, "gallery", 0, [{"id": "t3", "action": "erase"}])
    assert r["ok"] and cloud[0]["transform"] == "e_gen_remove:region_((x_32;y_1392;w_736;h_96))"


# ── 4·5. 글자 고치기 · 되돌리기 ───────────────────────────────────────────────────────────────

def test_fix_text_erases_then_overlays_noto_sans_kr(cloud):
    from src.services import image_edit as E
    ex = _ex()
    r = E.apply(ex, "gallery", 0, [{"id": "t5", "action": "text", "text": "이탈리아 감성 홈"}], small=_photo())
    assert r["ok"] and r["credits"] == 0.052                                   # gen_remove 50 + 기본 1 + 글자 1
    tr = cloud[0]["transform"]
    assert tr.startswith("e_gen_remove:region_((x_16;y_746;w_308;h_48))/")             # 상자 + 높이 10% 여유
    # Y11-L: 운영 Cloudinary가 「Noto Sans KR」을 400(Unsupported font family)으로 거부 — NanumGothic(한글 그림 확인)
    assert "l_text:NanumGothic_" in tr and "co_rgb:" in tr and "fl_layer_apply,g_north_west,x_20,y_" in tr
    assert ex["images_ko"][0]["edit"]["by"] == "user"


def test_second_edit_is_a_new_version_on_top_and_revert_steps_back(cloud):
    """Y11-E: 편집은 **고른 버전 위에 새 편집본**을 만든다. 「되돌리기」 = 바로 전 버전(편집본 2 → 1 → 번역본 → 원본)."""
    from src.services import image_edit as E
    from src.services import image_translate_store as S
    ex = _ex()
    E.apply(ex, "gallery", 0, [{"id": "t1", "action": "erase"}], small=_photo())
    first = ex["images_ko"][0]["url"]
    E.apply(ex, "gallery", 0, [{"id": "t2", "action": "erase"}], small=_photo())
    assert cloud[0]["src"].endswith("p0_TENCENT.jpg") and cloud[1]["src"] == first          # 편집본 2의 바탕 = 편집본 1
    assert cloud[1]["transform"].count("(x_") == 1                                            # 이번 상자만
    keys = [v["key"] for v in E.versions(ex, "gallery", 0)]
    assert keys == ["original", "translated", "edit:1", "edit:2"] and E.current_key(ex["images_ko"][0]) == "edit:2"
    assert E.plan(ex, "gallery", 0, small=_photo())["spent"] == 0.102
    assert E.revert(ex, "gallery", 0)["back"] == "edit:1" and ex["images_ko"][0]["url"] == first
    assert E.revert(ex, "gallery", 0)["back"] == "translated"
    e = ex["images_ko"][0]
    assert "edit" not in e and e["url"].endswith("p0_TENCENT.jpg") and S.promo_excluded(e)
    assert E.revert(ex, "gallery", 0)["back"] == "original" and e["use"] is False
    assert not E.revert(ex, "gallery", 0)["ok"]                                              # 원본에서 더 뒤는 없다
    assert [v["key"] for v in E.versions(ex, "gallery", 0)] == keys                         # 버전은 사라지지 않는다


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
    assert r["boxes"] == [{"x": 20, "y": 40, "w": 200, "h": 60, "src": "满300减50", "tgt": "", "conf": 99.0}]   # 1024로 보냈다 → ×2 · Y11-D 확신 같이


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
    from src.services import image_edit as E
    monkeypatch.setattr(E, "_ocr_version", lambda url: O.read_boxes(b"jpg"))     # 이 테스트는 OCR 호출 횟수를 센다
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11"
    d = c.get(f"/seller/collect/{iid}/image-edit/gallery/0").get_json()
    assert d["ok"] and [b["cls"] for b in d["boxes"] if b["id"].startswith("t")] == ["promo", "promo"] and len(seen) == 1
    d2 = c.get(f"/seller/collect/{iid}/image-edit/gallery/0").get_json()
    assert len(seen) == 1 and len(d2["boxes"]) == len(d["boxes"])             # 저장됨 — 다시 안 부른다
    r = c.post(f"/seller/collect/{iid}/image-edit/gallery/0", json={"ops": [{"id": "t0", "action": "erase"}]}).get_json()
    assert r["ok"] and r["credits"] == 0.051 and r["plan"]["edit"]["url"].endswith("edit.jpg")
    # Y11-E: 상자는 버전에 붙는다 — 편집본은 그 그림을 한 번 OCR로 읽는다(번역본 상자를 편집본 위에 그대로 그리지 않는다)
    assert r["plan"]["current"] == "edit:1" and len(seen) == 2
    d3 = c.get(f"/seller/collect/{iid}/image-edit/gallery/0").get_json()
    assert len(seen) == 2 and d3["current"] == "edit:1"                        # 저장됨 — 다시 안 부른다
    rv = c.post(f"/seller/collect/{iid}/image-edit/gallery/0/revert", json={}).get_json()
    assert rv["ok"] and rv["back"] == "translated"


def test_old_picture_without_text_entry_is_not_a_failure_badge(monkeypatch):
    """캡처에서 잡힘 — 예전에 「실패」로 저장된 글자 없는 사진(PictureWithoutText)이 카드에 빨간 「이미지 번역 실패」로 떴다."""
    from src.services import image_translate_auto as A
    monkeypatch.setattr(A, "status", lambda item_id: {})
    ex = {"images_ko": [{"idx": 4, "status": "failed", "error_code": "UnsupportedOperation.PictureWithoutText",
                         "error_message": "翻译失败，输入为无文本图片。"}]}
    assert A.item_failure("x", ex) == {}
    ex["images_ko"].append({"idx": 5, "status": "failed", "error_code": "FailedOperation.Timeout", "error_message": "timeout"})
    assert A.item_failure("x", ex)["failed"] == 1


def test_gallery_job_input_goes_through_y9_normalization(monkeypatch):
    """실측 14:49: 갤러리 「번역」 작업(`image_translate_job` → `translate_image(url=…)`)이 대표사진 picasso.jpg를 그대로 보내
    `InvalidParameterValue.Data`. 정규화(webp·gif → JPEG · 긴 변 ≤ 4096 · ≤ 4MB)는 상세 큐 경로에만 있었다 → 공급사 앞 한 곳으로.
    ⚠️ 그 picasso.jpg 바이트는 여기서 못 받는다(alicdn 차단) — Y9에서 확인된 원인 두 가지(이름은 .jpg인데 내용은 webp · 너무 큼)로 재현."""
    import base64
    from unittest.mock import patch
    from PIL import Image
    from src.services import image_translate_tencent as tc
    sent = []

    class _Resp:
        Data = "aW1n"
        Source, Target, SourceText, TargetText = "zh", "ko", "满300减50", "300 이상 50 할인"
        TransDetails, RequestId, Angle = [], "req-1", 0

    class _Cli:
        def ImageTranslateLLM(self, req):
            sent.append(base64.b64decode(req._serialize()["Data"]))
            return _Resp()

    def webp_bytes():
        b = io.BytesIO()
        Image.new("RGB", (800, 800), (200, 90, 40)).save(b, "WEBP")
        return b.getvalue()

    def big_jpeg():
        b = io.BytesIO()
        Image.new("RGB", (5000, 1000), (255, 255, 255)).save(b, "JPEG", quality=70)
        return b.getvalue()

    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    pic = "https://gw.alicdn.com/imgextra/O1CN01wRKL8oChG0I2vHAO_!!2210826600484-0-picasso.jpg"
    for raw, want in ((webp_bytes(), (800, 800)), (big_jpeg(), (4096, 819))):
        with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), patch.object(tc, "fetch_image", lambda u: (raw, "")):
            out = tc.translate_image(url=pic)
        assert out["ok"] and sent[-1][:2] == b"\xff\xd8" and out["converted"]
        with Image.open(io.BytesIO(sent[-1])) as im:
            assert im.format == "JPEG" and im.size == want and out["sent_size"] == list(want)
    ok_jpeg = io.BytesIO()
    Image.new("RGB", (750, 1000), (255, 255, 255)).save(ok_jpeg, "JPEG")
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), patch.object(tc, "fetch_image", lambda u: (ok_jpeg.getvalue(), "")):
        out = tc.translate_image(url=pic)
    assert sent[-1] == ok_jpeg.getvalue() and "converted" not in out                # 이미 한도 안 JPEG는 다시 굽지 않는다
    from src.services import image_translate_job as job                       # 갤러리 「번역」 작업 그대로 돌린다
    store = {"extra": {"images": [pic]}}
    monkeypatch.setattr(job, "_load", lambda item_id, ids: ({"id": item_id}, store["extra"]))
    monkeypatch.setattr(job, "_save", lambda item_id, ids, extra: store.update(extra=extra) or True)
    from src.services import image_translate_store as istore
    monkeypatch.setattr(istore, "record_usage", lambda *a, **k: None)
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), patch.object(tc, "fetch_image", lambda u: (webp_bytes(), "")):
        job._run("vrsuk", "u", [0], {"u"})
    assert sent[-1][:2] == b"\xff\xd8" and store["extra"]["images_ko"][0]["status"] == "done"


def test_photo_without_text_route_has_no_boxes_and_nothing_to_erase(cloud):
    """글자 없는 사진(번역 결과 PictureWithoutText) → 상자 0 · 지울 것 없음 · 번역 다시 하라고도 안 함 · 보내도 거절."""
    from src.seller_console import collect_history_store as S
    from src.order_webhook import app
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id="y11d", title="x",
                   price="1", currency="CNY", extra=_ex())
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11d"
    d = c.get(f"/seller/collect/{iid}/image-edit/gallery/4").get_json()
    assert d["ok"] and d["boxes"] == [] and d["why"] == "이 사진에서 글자를 못 찾았어요 — 지울 것이 없어요" and not d["need_translate"]
    r = c.post(f"/seller/collect/{iid}/image-edit/gallery/4", json={"ops": [{"id": "t0", "action": "erase"}]})
    assert r.status_code == 409 and "글자를 못 찾았어요" in r.get_json()["error"] and cloud == []
