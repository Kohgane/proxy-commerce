"""T-S1(오너 2026-10-02 폰 등록 16:06~16:09) — 「상세 1번째 — 우리 서버 주소라 마켓이 가져갈 수 없습니다」, 직전 사전검증 「통과」.

## 실측(운영 읽기 전용 · 「미야케 아키라…」 ae9cee70)
- 상세 1번째 = `//img.alicdn.com/imgextra/…shopmanager.jpg_1200x1200q30.jpg_.webp` — **우리 주소가 아니라 스킴 없는 공급사 주소**.
  확장이 `data-src` 원문을 그대로 보낸 모양이고, `is_internal`은 스킴·호스트가 없으면 우리 주소로 친다(문구가 틀렸다).
- 상세 2번째 = `gtms04.alicdn.com/tps/…-51-24.png`(51×24 아이콘). `detail_images_cdn` 없음 → CDN 사본도 없었다.
- 사전검증은 이미지 도달을 재지 않았다(대표 1장 HEAD만) — 도달 판정은 **등록에만** 있었다.

## 계약
  1 `//` 주소는 등록 배열에서 `https:`로 펴진다(프로토콜 상대 주소 — 발명 아님) → 도달 판정 통과
  2 사이트 상대 경로는 못 편다 — 이유를 「사이트가 빠져」로 말한다(「우리 서버 주소」는 진짜 우리 경로일 때만)
  3 사전검증이 **등록과 같은 함수**(`_outbound_images`)로 배열을 만들고 도달을 잰다 — 못 가져가면 사전검증에서 막힘
  4 보내기 직전, 아직 우리 주소/상대 경로인 장은 그 상품만 Cloudinary로 올리고(원본: 소스 페이지 기준) 그 주소로 나간다
"""
from __future__ import annotations

import json

import pytest
from tests._pv_helper import prevalidate as _pv   # Z9: 사전검증은 202 + 잡(폴링)

OWNER_DETAIL = ["//img.alicdn.com/imgextra/i1/1116632222/O1CN01SGQy8H1SHiuTtVrP9_!!1116632222-0-shopmanager.jpg_1200x1200q30.jpg_.webp",
                "https://gtms04.alicdn.com/tps/i4/TB1lLP.HpXXXXb5XpXXaYjxHXXX-51-24.png_.webp"]
CDN = "https://res.cloudinary.com/x/image/upload/v1/orig.jpg"


def test_scheme_relative_detail_goes_out_as_https():
    from src.services import image_translate_store as S
    from src.services.image_reachability import is_internal
    ex = {"images": ["https://img.alicdn.com/g1.jpg"], "detail_images": list(OWNER_DETAIL)}
    out = S.effective_images(ex, kind="detail")
    assert out[0] == "https:" + OWNER_DETAIL[0] and not is_internal(out[0])
    assert S.outbound_missing(ex) == []                                   # 올릴 장 0(이미 열린다)
    assert ex["detail_images"][0] == OWNER_DETAIL[0]                     # 원본 배열은 그대로


def test_reasons_tell_missing_site_from_our_server():
    from src.services.image_reachability import check_one
    assert check_one("/seller/collect/image-ko/x/0")["reason"] == "우리 서버 주소라 마켓이 가져갈 수 없습니다"
    assert "사이트(https://…)가 빠져" in check_one("/imgextra/d.jpg")["reason"]


@pytest.fixture
def client(monkeypatch):
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import PrevalidationResult

    class _Disp:
        def prevalidate(self, product, markets):
            _Disp.seen = product
            return [PrevalidationResult(market=m, ok=True, message="사전검증 통과") for m in markets]

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _Disp())
    import src.services.image_reachability as R
    real = R.check_one
    # 외부 주소는 네트워크 대신 「열림」으로(이 환경은 공급사 CDN이 막혀 있다) — 판정 대상은 우리가 내보내는 주소 모양
    monkeypatch.setattr(R, "check_one", lambda u: real(u) if R.is_internal(u) else
                        {"url": u, "ok": True, "status": 200, "content_type": "image/jpeg", "reason": ""})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-s1"
    c.disp = _Disp
    return c


def _item(detail):
    from src.seller_console import collect_history_store as S
    ex = {"title": "플리츠 셔츠", "price": "199", "currency": "CNY",
          "images": ["https://img.alicdn.com/g1.jpg"], "detail_images": list(detail)}
    return S.append(source="extension", url="https://item.taobao.com/item.htm?id=999609404643", title="플리츠 셔츠",
                    price="199", currency="CNY", extra=ex, seller_id="u-s1")


def test_prevalidate_measures_what_registration_sends(client):
    iid = _item(OWNER_DETAIL)
    product = {"title": "플리츠 셔츠", "price": "199", "images": ["https://img.alicdn.com/g1.jpg"],
               "detail_images": list(OWNER_DETAIL)}
    d = _pv(client, {"product": product, "markets": ["coupang"], "item_id": iid})
    assert d["results"][0]["ok"] is True                                  # `//`가 펴져 통과(오너 상품 그대로)
    assert client.disp.seen["detail_images"][0].startswith("https://img.alicdn.com/")


def test_prevalidate_blocks_what_registration_would_block(client, monkeypatch):
    import src.services.image_cdn_backfill as BF
    monkeypatch.setattr(BF, "cdn_ready", lambda: False)                  # CDN 없음 → 상대 경로는 못 고친다
    iid = _item(["/imgextra/d1.jpg"])
    product = {"title": "플리츠 셔츠", "price": "199", "images": ["https://img.alicdn.com/g1.jpg"],
               "detail_images": ["/imgextra/d1.jpg"]}
    d = _pv(client, {"product": product, "markets": ["coupang"], "item_id": iid})
    r = d["results"][0]
    assert r["ok"] is False and r["error_code"] == "image_unreachable"
    assert r["message"].startswith("등록 전 이미지 확인에서 막혔어요") and any("상세 1번째" in x for x in r["details"])
    up = client.post("/seller/collect/upload", json={"product": product, "markets": ["coupang"], "item_id": iid})
    assert up.status_code == 409 and up.get_json()["step"] == "도달성 확인"   # 등록도 같은 판정


def test_send_time_upload_replaces_unreachable_pages(client, monkeypatch):
    import src.services.image_cdn_backfill as BF
    fetched = []
    monkeypatch.setattr(BF, "cdn_ready", lambda: True)
    monkeypatch.setattr(BF, "fetch_original", lambda u, **kw: fetched.append((u, kw.get("base_url"))) or (b"jpeg", ""))
    monkeypatch.setattr(BF, "_upload", lambda raw, label=None: (CDN, ""))
    iid = _item(["/imgextra/d1.jpg"])
    product = {"title": "플리츠 셔츠", "price": "199", "images": ["https://img.alicdn.com/g1.jpg"],
               "detail_images": ["/imgextra/d1.jpg"]}
    d = _pv(client, {"product": product, "markets": ["coupang"], "item_id": iid})
    assert d["results"][0]["ok"] is True and client.disp.seen["detail_images"] == [CDN]
    assert fetched and fetched[0][1].startswith("https://item.taobao.com/")   # 상대 경로는 소스 페이지 기준
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(iid, seller_ids={"u-s1"})["extra_json"])
    assert ex["detail_images_cdn"] == {"0": CDN} and ex["detail_images"] == ["/imgextra/d1.jpg"]


def test_screens_send_item_id_to_prevalidate():
    from pathlib import Path
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "markets: markets, item_id: itemId" in m5
    # Y2 후속(2026-10-04): 같은 몸통에 refresh_from_store가 붙었다 — item_id를 싣는다는 계약은 그대로
    assert "JSON.stringify({product: buildProductData(), markets, item_id: _ITEM_ID," in pv
