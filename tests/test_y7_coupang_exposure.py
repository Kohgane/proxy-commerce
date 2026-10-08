"""Y7(오너 2026-10-04) — 「쿠팡 노출」 미리보기 + 대표 사진 자동 판정 + 사전검증 보류·그래도 등록.

시나리오(오너 지정): 블랙홀 램프 — 1번 이미지에 「INTERSTELLAR」 글자가 박혀 있다 → 「텍스트 있음」 경고·쿠팡 보류,
2번을 대표로 바꾸면 통과. 이미지는 PIL로 그린 합성본(네트워크 0 — 내려받기는 대역).
"""
from __future__ import annotations

import io
import json

import pytest
from tests._pv_helper import prevalidate as _pv   # Z9: 사전검증은 202 + 잡(폴링)

URL1 = "https://img.alicdn.com/blackhole-1.jpg"
URL2 = "https://img.alicdn.com/blackhole-2.jpg"
URL_SMALL = "https://img.alicdn.com/tiny.jpg"


def _png(size=(800, 800), text="", bg=(255, 255, 255)):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.ellipse((size[0] * .25, size[1] * .25, size[0] * .75, size[1] * .75), fill=(20, 20, 30))   # 램프 몸통
    if text:
        d.text((size[0] * .08, size[1] * .82), text, fill=(10, 10, 10), font=ImageFont.load_default(size=72))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


IMG = {URL1: _png(text="INTERSTELLAR"), URL2: _png(), URL_SMALL: _png((400, 300))}


@pytest.fixture
def wired(monkeypatch):
    from src.services import coupang_image_check as C
    from src.services import image_text_precheck as P
    from src.services import image_translate_tencent as tc
    monkeypatch.setenv("COUPANG_IMAGE_CHECK", "1")
    C.reset_cache()
    monkeypatch.setattr(tc, "fetch_image", lambda u: (IMG[u], "") if u in IMG else (b"", "못 받음"))
    # OCR 대역: 글자를 그린 장만 「INTERSTELLAR」(엔진 실측은 아래 skipif 테스트)
    monkeypatch.setattr(P, "all_text", lambda raw: (True, "INTERSTELLAR") if raw == IMG[URL1] else (False, ""))
    yield C
    C.reset_cache()


def _item(seller, images):
    from src.seller_console import collect_history_store as S
    ex = {"title": "星际穿越黑洞氛围灯", "title_ko": "블랙홀 무드등 인테리어 조명", "price": "69.90", "currency": "CNY",
          "images": images, "options": [], "skus": []}
    return S.append(source="extension", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id=seller,
                    title=ex["title_ko"], price="69.90", currency="CNY", extra=ex)


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller; s["user_role"] = "admin"   # Z6: 서버 env 키(오너 자격)는 공유 사용자만
    return c


def test_check_bytes_size_square_white_and_text(wired):
    c = wired.check_bytes(IMG[URL1])
    assert c["state"] == "ok" and (c["w"], c["h"]) == (800, 800) and c["square"] and not c["small"]
    assert c["text"] is True and any(f["line"] == "텍스트 있음 — 반려 가능(읽은 글자 「INTERSTELLAR」)" for f in c["flags"])
    assert c["white_pct"] >= 90                                         # 흰 바탕(가장자리 띠)
    s = wired.check_bytes(IMG[URL_SMALL])
    keys = {f["key"] for f in s["flags"]}
    assert keys == {"small", "not_square"} and "반려 예상 — 500px 미만(긴 변 400px)" in [f["line"] for f in s["flags"]]


def _settle(c, iid, d, tries=100):
    """Y6-C B: 대표 사진 판정은 요청 밖(백그라운드)에서 — 화면처럼 /check를 물어 결과가 오면 그 값으로."""
    import time
    for _ in range(tries):
        if d["check"].get("state") != "pending":
            return d
        r = c.get(f"/seller/collect/{iid}/coupang-exposure/check", query_string={"rep": d["rep"]}).get_json()
        if r["check"].get("state") != "pending":
            return dict(d, check=r["check"], hold=r["hold"])
        time.sleep(0.05)
    raise AssertionError("판정이 끝나지 않았다")


def test_blackhole_lamp_text_holds_then_image2_as_rep_passes(wired):
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.seller_console import collect_history_store as S
    seller = "owner-y7"
    iid = _item(seller, [URL1, URL2])
    c = _client(seller)
    d = c.get(f"/seller/collect/{iid}/coupang-exposure").get_json()
    assert d["ok"] and d["rep"] == URL1 and d["check"]["state"] in ("pending", "ok")   # 요청은 OCR을 기다리지 않는다
    d = _settle(c, iid, d)
    assert d["check"]["text"] is True
    assert d["hold"]["fix"] == "rep_image" and "텍스트 있음" in d["hold"]["short"]
    pd = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    h = [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"] == "rep_image"]
    assert h and "INTERSTELLAR" in h[0]["line"]
    assert not [h for h in UploadDispatcher.readiness_holds(pd, "smartstore") if h["fix"] == "rep_image"]   # 쿠팡만
    # 2번을 대표로
    d2 = _settle(c, iid, c.post(f"/seller/collect/{iid}/rep-image", json={"idx": 1}).get_json())
    assert d2["rep"] == URL2 and d2["hold"] is None and d2["check"]["text"] is False
    assert [s["original"] for s in d2["strip"]] == [URL2, URL1] and d2["strip"][0]["rep"]
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["images"] == [URL1, URL2] and ex["rep_image"] == URL2   # 원본 배열은 그대로 — 대표만 적는다
    pd2 = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    assert pd2["images_effective"][0] == URL2
    assert not [h for h in UploadDispatcher.readiness_holds(pd2, "coupang") if h["fix"] == "rep_image"]


def test_small_rep_holds_and_override_is_per_image(wired):
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    from src.seller_console import collect_history_store as S
    seller = "owner-y7-small"
    iid = _item(seller, [URL_SMALL, URL1])
    c = _client(seller)
    pd = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    holds = UploadDispatcher.readiness_holds(pd, "coupang")
    rh = next(h for h in holds if h["fix"] == "rep_image")
    assert "500px 미만" in rh["short"] and "「쿠팡 노출」 탭에서 대표 사진을 바꾸거나 「그래도 등록」" in readiness_message(holds)
    o = c.post(f"/seller/collect/{iid}/rep-image-override", json={}).get_json()
    assert o["ok"] and o["override"]["url"] == URL_SMALL
    pd = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    assert not [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"] == "rep_image"]
    # 대표를 다른 장(글자 있는 1번)으로 바꾸면 그 「그래도 등록」은 안 따라간다 — 다시 잰다
    c.post(f"/seller/collect/{iid}/rep-image", json={"idx": 1})
    pd = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    assert [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"] == "rep_image"]


def test_unreadable_image_does_not_hold(wired):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"images_effective": ["https://img.alicdn.com/missing.jpg"], "price": "1", "title": "x"}
    assert not [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"] == "rep_image"]
    assert wired.check_url("https://img.alicdn.com/missing.jpg")["state"] == "unknown"


def test_prevalidate_route_sees_new_rep_and_override(wired, monkeypatch):
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID", "COUPANG_VENDOR_USER_ID",
              "COUPANG_RETURN_CENTER_CODE", "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", "COUPANG_RETURN_ZIP_CODE",
              "COUPANG_RETURN_ADDRESS", "COUPANG_RETURN_CHARGE_NAME", "COUPANG_COMPANY_CONTACT_NUMBER"):
        monkeypatch.setenv(k, "x1")
    import urllib.request
    from src.services import image_reachability as R
    monkeypatch.setattr(R, "check_all", lambda *a, **k: None)          # 네트워크 0(도달 측정은 이 계약 밖)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    seller = "owner-y7-pv"
    iid = _item(seller, [URL1, URL2])
    c = _client(seller)
    body = {"item_id": iid, "markets": ["coupang"], "product": {"title": "블랙홀 무드등 인테리어 조명", "price": "69.90",
            "currency": "CNY", "images": [URL1, URL2], "images_effective": [URL1, URL2]}}
    r = next(x for x in _pv(c, body)["results"] if x["market"] == "coupang")
    assert r["hold"] and "rep_image" in r["fixes"]
    c.post(f"/seller/collect/{iid}/rep-image", json={"idx": 1})
    r = next(x for x in _pv(c, body)["results"] if x["market"] == "coupang")
    assert "rep_image" not in (r.get("fixes") or [])                 # 화면이 보낸 묵은 목록이 아니라 저장된 대표로 잰다


def test_rep_image_route_rejects_bad_index(wired):
    seller = "owner-y7-bad"
    iid = _item(seller, [URL1, URL2])
    assert _client(seller).post(f"/seller/collect/{iid}/rep-image", json={"idx": 5}).status_code == 400


def test_tab_and_m5_share_one_partial():
    from pathlib import Path
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    part = Path("src/seller_console/templates/_coupang_exposure.html").read_text(encoding="utf-8")
    assert 'data-etab="cpx"' in pv and pv.count('{% include "_coupang_exposure.html" %}') == 1
    assert m5.count('{% include "_coupang_exposure.html" %}') == 1
    for role in ("cpx-card", "cpx-checks", "cpx-strip", "cpx-rep", "cpx-use", "cpx-override", "cpx-view-orig"):
        assert f'data-role="{role}"' in part
    assert "pv-rep-override" in pv and "m5-rep-override" in m5


def test_ocr_reads_interstellar_via_tencent_ocr(monkeypatch):
    """Z7: 글자 판정은 텐센트 OCR API — 「INTERSTELLAR」 조각이 오면 텍스트 있음, 조각 없으면 없음(대역은 공급사 응답만)."""
    from src.services import image_text_precheck as P
    from src.services import ocr_tencent as O
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: {"TextDetections": [{"DetectedText": "INTERSTELLAR", "Confidence": 99}]})
    has, seen = P.all_text(IMG[URL1])
    assert has is True and "INTERSTELLAR" in seen.replace(" ", "").upper()
    monkeypatch.setattr(O, "_call", lambda b64: {"TextDetections": [{"DetectedText": "x", "Confidence": 30}]})
    assert P.all_text(IMG[URL2])[0] is False                           # 확신 50 미만 조각은 버린다
