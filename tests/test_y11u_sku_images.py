"""Y11-U(오너 2026-10-16 14:58) — 옵션(SKU) 사진도 이미지 번역·소품·판촉 규칙에 태운다.

- `kind="sku"` = 수집 원본 `skus[].image`(중복 없이 나온 순서) ↔ `extra.sku_images_ko`.
- 등록은 SKU마다 번역본으로 바꿔 끼고(원본 `extra.skus`는 그대로), SKU 사진은 빼거나 순서를 바꾸지 않는다.
- 쿠팡 등록본 갱신은 옵션 대표 사진 + 정가 = 판매가를 함께 얹는다.
"""
import json

import pytest

from src.services import image_translate_store as its


SKUS = [
    {"sku_id": "s1", "spec": ["棕色半皮"], "image": "https://img.example.com/a.jpg"},
    {"sku_id": "s2", "spec": ["黑色全皮"], "image": "https://img.example.com/b.jpg"},
    {"sku_id": "s3", "spec": ["棕色全皮"], "image": "https://img.example.com/a.jpg"},   # 같은 사진 공유
    {"sku_id": "s4", "spec": ["灰色"], "img": "https://img.example.com/c.jpg"},
]
KO = "https://res.cloudinary.com/x/image/upload/ko-b.jpg"


def _extra(**over):
    ex = {"skus": [dict(s) for s in SKUS],
          "sku_images_ko": [{"idx": 1, "status": "done", "use": True, "url": KO}]}
    ex.update(over)
    return ex


def test_kinds_and_keys():
    assert its.KINDS == ("gallery", "detail", "sku")
    assert its.keys_of("sku") == ("sku_images", "sku_images_ko")
    assert its.keys_of("detail") == ("detail_images", "detail_images_ko")
    assert its.keys_of("bogus") == ("images", "images_ko")
    assert its.parse_kind("sku") == "sku" and its.parse_kind("x") == "gallery"


def test_sku_originals_dedup_in_order():
    assert its.sku_images_of(_extra()) == ["https://img.example.com/a.jpg", "https://img.example.com/b.jpg",
                                          "https://img.example.com/c.jpg"]
    assert its.originals_of(_extra(), "sku") == its.sku_images_of(_extra())


def test_sku_effective_is_one_to_one_even_with_promo():
    """판촉 글자가 있어도 SKU 사진은 빼지 않는다(자리로 SKU와 짝) — 「지우기 제안」만."""
    ex = _extra(sku_images_ko=[{"idx": 0, "status": "done", "use": True, "url": KO, "promo": True},
                               {"idx": 1, "status": "done", "use": True, "url": KO}])
    out = its.effective_images(ex, kind="sku")
    assert len(out) == 3 and out[0] == KO and out[1] == KO and out[2].endswith("c.jpg")


def test_sku_image_map_only_changed():
    assert its.sku_image_map(_extra()) == {"https://img.example.com/b.jpg": KO}
    assert its.sku_image_map({"skus": []}) == {}


def test_apply_sku_images_copies_and_keeps_original():
    from src.seller_console.views import apply_sku_images
    ex = _extra()
    out = apply_sku_images(ex["skus"], its.sku_image_map(ex))
    assert out[1]["image"] == KO and out[0]["image"].endswith("a.jpg")
    assert ex["skus"][1]["image"].endswith("b.jpg")                 # 수집 원본은 그대로
    assert apply_sku_images(ex["skus"], {}) is ex["skus"]


def test_translate_plan_includes_sku_pages():
    from src.services import image_translate_auto as A
    plan = A.translate_plan({"skus": [dict(s) for s in SKUS]}, retry=True)
    sent = [(k, i) for k, i, *_ in plan["send"] if k == "sku"]
    assert sent == [("sku", 0), ("sku", 1), ("sku", 2)]
    assert A.per_item_cap("sku") >= 3


def test_patch_items_sets_option_image_and_list_price():
    from src.services import coupang_detail_refresh as R
    body = {"items": [
        {"externalVendorSku": "s2", "salePrice": 3601500, "originalPrice": 3601500,   # #921로 나간 상태(정가=판매가)
         "images": [{"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": "https://old/b.jpg"},
                    {"imageOrder": 1, "imageType": "DETAIL", "vendorPath": "https://old/d.jpg"}]},
        {"externalVendorSku": "s1", "salePrice": 100, "originalPrice": 100, "images": []},
    ]}
    tg = {"contents": [{"contentsType": "TEXT"}], "sku_images": {"s2": KO}}
    n = R.patch_items(body, tg)
    a, b = body["items"]
    assert n == {"images": 1, "list_price": 1}                       # s1: 100 ×1.15 = 115 → 100원 반올림 100(그대로)
    assert a["images"][0] == {"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": KO}
    assert a["images"][1]["vendorPath"] == "https://old/d.jpg" and a["originalPrice"] == 4141700   # 원복 — 원래 표시 정가
    assert b["images"] == [] and b["contents"] == tg["contents"]


def test_sku_image_patch_maps_by_original_sku(monkeypatch):
    """등록 빌더가 이미 번역본으로 바꿔 낀 skus를 줘도 — 수집 원본 SKU 주소로 짝을 찾는다."""
    from src.services import coupang_detail_refresh as R
    item = {"id": "it", "extra_json": json.dumps(_extra())}
    pd = {"skus": [dict(s, image=KO) for s in SKUS]}
    assert R._sku_image_patch(item, pd) == {"s2": KO}


def test_hash_changes_when_option_image_joins(monkeypatch):
    from src.services import coupang_detail_refresh as R
    a = R._hash({"contents": [1], "sku_images": {}, "list_price": "markup:15"})
    b = R._hash({"contents": [1], "sku_images": {"s2": KO}, "list_price": "markup:15"})
    assert a != b


@pytest.fixture
def qstate(monkeypatch):
    from src.db import image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: box.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, v))
    return box


def test_enqueue_item_once_per_coupang_upload(qstate):
    from src.services import coupang_detail_refresh as R
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785"},
                       {"market": "coupang:woojoo", "product_id": "16415921999"},
                       {"market": "smartstore:chezgoga", "product_id": "1"}]}
    assert R.enqueue_item("it", ex, "u1") == 2
    assert R.enqueue_item("it", ex, "u1") == 0                       # 이미 서 있으면 그대로
    rows = R.queue_rows()
    assert {r["market"] for r in rows} == {"coupang:gogane", "coupang:woojoo"}
    assert all(r["reason"] == R.SKU_IMAGE_REASON for r in rows)


def test_after_sku_translated_waits_for_last_page(qstate, monkeypatch):
    from src.services import image_translate_auto as A
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785"}]}

    class Q:
        def __init__(self, c):
            self.c = c

        def counts(self, item_id):
            return self.c
    monkeypatch.setattr(A, "_q", lambda: Q({"queued": 2, "running": 1}))
    A._after_sku_translated("it", "u1", ex)
    assert not (qstate.get("coupang_detail_refresh:queue") or {}).get("rows")
    monkeypatch.setattr(A, "_q", lambda: Q({"queued": 0, "running": 1}))
    A._after_sku_translated("it", "u1", ex)
    assert len(qstate["coupang_detail_refresh:queue"]["rows"]) == 1


def test_sku_option_rows_labels_and_promo(monkeypatch):
    from src.seller_console.views import sku_option_rows
    ex = _extra(sku_images_ko=[{"idx": 1, "status": "done", "use": True, "url": KO,
                                "lines": [{"src": "正品保障", "dst": "정품 보장"}]}])
    rows = sku_option_rows(ex)
    assert [r["idx"] for r in rows] == [0, 1, 2]
    assert rows[1]["url"] == KO and rows[0]["url"].endswith("a.jpg")
    assert len(rows[0]["labels"]) == 2                               # 두 SKU가 같은 사진
    assert sku_option_rows({"skus": []}) == []


def test_badge_hits_warranty_badges_longest_only():
    from src.services import detail_image_plan as d
    assert d.badge_hits("【棕色半皮】正品保障 20年质保 정품 보장 20년 품질 보증") == ["正品保障", "20年质保", "정품 보장", "20년 품질 보증"]
    assert d.badge_hits("브라운 반가죽") == []


def test_sku_option_rows_promo_badges_are_suggested_not_dropped():
    from src.seller_console.views import sku_option_rows
    ex = _extra(sku_images_ko=[{"idx": 0, "status": "done", "use": True, "url": KO,
                                "source_text": "正品保障 20年质保", "target_text": "정품 보장 20년 품질 보증"}])
    rows = sku_option_rows(ex)
    assert len(rows) == 3 and rows[0]["url"] == KO
    assert "正品保障" in rows[0]["promo"] and "20年质保" in rows[0]["promo"]
    plan = its.effective_plan(ex, kind="sku")
    assert all(p["promo_excluded"] is False for p in plan)


def test_polish_targets_include_sku():
    from src.services import image_polish as P
    from src.services import image_translate_store as istore
    e = {"idx": 1, "status": "done", "use": True, "url": KO, "boxes": [{"src": "头层", "tgt": "소가죽"}]}
    if not istore.has_boxes(e):
        pytest.skip("상자 구조가 다름")
    assert ("sku", 1) in P.item_targets({"skus": SKUS, "sku_images_ko": [e]})
