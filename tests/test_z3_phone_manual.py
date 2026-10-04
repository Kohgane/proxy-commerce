"""Z3(c)(오너 2026-10-04) — 폰만 쓰는 유저의 최후 경로: 담은 화면에서 사진(앨범 여러 장)·옵션 직접 입력 → 등록으로.

실측: 오늘 share 3건(item.taobao 733241700286 등)이 제목 없음·사진 0·옵션 0 — PC 확장이 없으면 영영 빈칸이었다.
"""
from __future__ import annotations

import io
import json

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def _item(seller, extra=None):
    from src.seller_console import collect_history_store as S
    ex = {"title": "", "price": "798", "currency": "CNY", "images": [], "uncollected": ["images", "options", "description"],
          "enrich_state": "pending", "share_raw": "https://e.tb.cn/h.x?tk=y"}
    ex.update(extra or {})
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=733241700286", seller_id=seller,
                   title="", price="798", currency="CNY", extra=ex)
    return iid, S


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _ex(S, iid, seller):
    return json.loads(S.get(iid, seller_ids={seller})["extra_json"])


def test_phone_photos_go_to_the_gallery_and_bad_files_say_why(monkeypatch):
    import src.media.image_pipeline as IP
    n = {"i": 0}

    def fake_upload(raw, **kw):
        n["i"] += 1
        return {"ok": True, "secure_url": f"https://res.cloudinary.com/x/manual/{n['i']}.jpg", "error": ""}
    monkeypatch.setattr(IP, "upload_bytes", fake_upload)
    seller = "owner-z3-photo"
    iid, S = _item(seller)
    c = _client(seller)
    r = c.post(f"/seller/collect/{iid}/manual-photos", content_type="multipart/form-data",
               data={"photos": [(io.BytesIO(PNG), "a.png", "image/png"), (io.BytesIO(JPG), "b.jpg", "image/jpeg"),
                                (io.BytesIO(b"hello"), "c.txt", "text/plain")]}).get_json()
    assert r["ok"] and r["added"] == 2 and r["images_count"] == 2
    assert len(r["failed"]) == 1 and "사진 파일이 아니에요" in r["failed"][0]
    ex = _ex(S, iid, seller)
    assert ex["images"] == ["https://res.cloudinary.com/x/manual/1.jpg", "https://res.cloudinary.com/x/manual/2.jpg"]
    assert "images" in ex["manual_fields"] and ex["field_sources"]["images"] == "manual"
    assert "images" not in ex["uncollected"]


def test_upload_failure_is_honest(monkeypatch):
    import src.media.image_pipeline as IP
    monkeypatch.setattr(IP, "upload_bytes", lambda raw, **kw: {"ok": False, "error": "Cloudinary 자격 미설정"})
    seller = "owner-z3-photo-fail"
    iid, S = _item(seller)
    r = _client(seller).post(f"/seller/collect/{iid}/manual-photos", content_type="multipart/form-data",
                             data={"photos": [(io.BytesIO(PNG), "a.png", "image/png")]})
    d = r.get_json()
    assert r.status_code == 502 and not d["ok"] and "Cloudinary 자격 미설정" in d["failed"][0]
    assert _ex(S, iid, seller)["images"] == []                            # 가짜 성공 0


def test_manual_options_make_skus_at_one_stated_price_and_survive_enrich(monkeypatch):
    seller = "owner-z3-opt"
    iid, S = _item(seller, {"title": "격스판 빈백 소파"})
    c = _client(seller)
    r = c.post(f"/seller/collect/{iid}/manual-options", json={
        "options": [{"name": "색상", "values": "블랙, 그레이"}, {"name": "사이즈", "values": "소형,대형"}],
        "price": ""}).get_json()
    assert r["ok"] and r["sku_count"] == 4 and r["price"] == "798"
    ex = _ex(S, iid, seller)
    assert ex["options"] == [{"name": "색상", "values": ["블랙", "그레이"]}, {"name": "사이즈", "values": ["소형", "대형"]}]
    assert {tuple(s["spec"]) for s in ex["skus"]} == {("블랙", "소형"), ("블랙", "대형"), ("그레이", "소형"), ("그레이", "대형")}
    assert all(s["price"] == "798" and s["source"] == "manual_same_price" for s in ex["skus"])
    assert "options" in ex["manual_fields"] and "sku" in ex["manual_fields"]
    # 뒤에 보강이 돌아도 직접 넣은 옵션은 그대로
    import src.api.extension_api as E
    monkeypatch.setattr(E, "_require_token", lambda scopes=None: {"user_id": seller})
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "title": "格斯潘懒人沙发", "options": [{"name": "颜色", "values": ["黑"]}],
                                           "page_diag": {"sel": {"title": 9, "detail": 3}}})
    assert _ex(S, iid, seller)["options"][0]["name"] == "색상"


def test_bad_options_are_rejected():
    seller = "owner-z3-opt-bad"
    iid, _S = _item(seller)
    c = _client(seller)
    d = c.post(f"/seller/collect/{iid}/manual-options", json={"options": [{"name": "색상", "values": ""}]}).get_json()
    assert not d["ok"] and "값이 비었어요" in d["error"]
    d = c.post(f"/seller/collect/{iid}/manual-options", json={"options": [{"name": "", "values": "블랙"}]}).get_json()
    assert not d["ok"] and "옵션 이름" in d["error"]


def test_phone_card_shows_manual_block_and_honest_line():
    seller = "owner-z3-card"
    iid, _S = _item(seller)
    h = _client(seller).get(f"/seller/m/item/{iid}").get_data(as_text=True)
    for s in ('data-role="m5-manual"', 'data-role="m5-photo-add"', 'accept="image/*" multiple',
              'data-role="m5-opt-save"', 'data-role="m5-to-register"', "PC 크롬 + 고가수집기가 있는 계정만"):
        assert s in h, s
    assert "컴퓨터에서 고가수집기를 켜면 자동으로" not in h


def test_screen_d_guide_is_public():
    from src.order_webhook import app
    h = app.test_client().get("/seller/guide/iphone/photos").get_data(as_text=True)
    assert "폰에서 사진·옵션 넣기" in h and all(f'data-role="step-d{k}"' in h for k in (1, 2, 3))
    assert "保存图片" in h and "「사진 추가」" in h and "「등록으로」" in h
