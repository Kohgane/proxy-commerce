"""오너 11-25 감독 3 — 흐린 사진으로 올라간 스스 상품(13892554342 · 13892554533 · 13894618263 · 13894618371)을 사진이 고쳐지면
「사진 다시 보내기」로 갱신(전송은 오너 탭 · 두 번 눌러야). 사진만 바꾸고 다른 칸은 조회한 값 그대로. 아직 작으면 안 보낸다."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MST = Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")


def test_update_images_changes_only_images(monkeypatch):
    import src.uploaders.naver_uploader as N
    calls = []
    op = {"statusType": "SALE", "name": "백팩", "salePrice": 59000,
          "images": {"representativeImage": {"url": "https://shop-phinf/old1.jpg"}, "optionalImages": [{"url": "https://shop-phinf/old2.jpg"}]}}

    def api(self, method, path, data=None, **kw):
        calls.append((method, path, data))
        return {"originProduct": op, "smartstoreChannelProduct": {"channelProductName": "백팩"}} if method == "GET" else {}
    monkeypatch.setattr(N.NaverSmartStoreUploader, "__init__", lambda self, account=None: None)
    monkeypatch.setattr(N.NaverSmartStoreUploader, "_api_request", api)
    up = N.NaverSmartStoreUploader()
    out = up.update_images("123", ["https://shop-phinf/new1.jpg", "https://shop-phinf/new2.jpg", "https://shop-phinf/new3.jpg"])
    assert out["success"] and out["before_n"] == 2 and out["after_n"] == 3
    put = [c for c in calls if c[0] == "PUT"][0][2]["originProduct"]
    assert put["images"] == {"representativeImage": {"url": "https://shop-phinf/new1.jpg"},
                             "optionalImages": [{"url": "https://shop-phinf/new2.jpg"}, {"url": "https://shop-phinf/new3.jpg"}]}
    assert put["name"] == "백팩" and put["salePrice"] == 59000                       # 다른 칸은 조회한 값 그대로


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def _item():
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=744111222333", title="tomtoc 백팩", price="129", currency="USD",
                    image="", seller_id="default", extra={"title_ko": "tomtoc 백팩", "images": ["https://img.example/a.jpg"],
                                                          "uploaded": [{"market": "smartstore", "product_id": "13894618000",
                                                                        "channel_product_no": "13894618263"}]})


def test_route_needs_confirm_and_naver_record(client):
    iid = _item()
    assert client.post(f"/seller/collect/{iid}/naver-resend-photos", json={"market": "smartstore"}).status_code == 400
    assert client.post(f"/seller/collect/{iid}/naver-resend-photos", json={"market": "coupang", "confirm": True}).status_code == 400


def test_route_refuses_while_photos_are_still_small(client, monkeypatch):
    import src.services.coupang_image_check as C
    monkeypatch.setattr(C, "size_of", lambda u: {"w": 320, "h": 320, "long_side": 320})
    iid = _item()
    d = client.post(f"/seller/collect/{iid}/naver-resend-photos", json={"market": "smartstore", "confirm": True}).get_json()
    assert d["ok"] is False and d["small"] is True and "320px" in d["error"]


def test_route_sends_and_records(client, monkeypatch):
    import src.services.coupang_image_check as C
    monkeypatch.setattr(C, "size_of", lambda u: {"w": 900, "h": 900, "long_side": 900})

    class _Up:
        def upload_images(self, urls):
            return {"ok": True, "urls": ["https://shop-phinf/n1.jpg"]}

        def update_images(self, no, urls):
            assert no == "13894618000" and urls == ["https://shop-phinf/n1.jpg"]
            return {"success": True, "before_n": 4, "after_n": 1}
    import src.channel_sync.smartstore_uploader as SU
    monkeypatch.setattr(SU, "make_uploader", lambda *a, **k: _Up())
    iid = _item()
    d = client.post(f"/seller/collect/{iid}/naver-resend-photos", json={"market": "smartstore", "confirm": True}).get_json()
    assert d["ok"] and d["after"] == 1 and d["before"] == 4
    from src.seller_console import collect_history_store as S
    rec = json.loads(S.get(iid, seller_id="default")["extra_json"])["uploaded"][0]
    assert rec["photo_resent"]["after"] == 1


def test_popup_button_needs_two_taps():
    assert 'data-role="mst-photo-resend"' in MST and "사진 다시 보내기" in MST
    assert "btn.getAttribute('data-armed') !== '1'" in MST and "한 번 더 누르면 네이버 사진을 바꿔요" in MST
    assert "'/naver-resend-photos'" in MST and "confirm: true" in MST
