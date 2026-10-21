"""Y14-f·g(오너 10-20 순찰 6) — 쿠팡 카테고리 바꾸기 = 새로 등록 → 새 상품 승인 → 옛 상품 판매중지(먼저 중지 금지) · 등록 뒤 표.

근거: 볼트 「쿠팡 API 지뢰」(2026-08-22~24 · 토라스 아우터 54건 · displayCategoryCode partial·전체 PUT 모두 미반영) +
10-20 피샹리 2계정 PUT 두 번 SUCCESS인데 조회 원문 77903. 판매중지 경로는 볼트 운영 스크립트(stop_sids.py 10-05)와 같다.
"""
import json

from src.services import coupang_relist as CR


def _item(extra):
    return {"id": "6f9c7ddf", "extra_json": json.dumps(extra, ensure_ascii=False)}


_EX = {"coupang_category_id": "77914",
       "uploaded": [{"market": "coupang:woojoo", "product_id": "16419632846", "account": "woojoo"}]}


class _Up:
    def __init__(self, new_status="승인완료", new_cat=77914, onsale_after=False):
        self.stopped, self.new_status, self.new_cat, self.onsale_after = [], new_status, new_cat, onsale_after

    def get_product(self, sid):
        if sid == "16419632846":
            return {"displayCategoryCode": 77903, "statusName": "승인완료",
                    "items": [{"vendorItemId": 9001}, {"vendorItemId": 9002}]}
        if sid == "16500000001":
            return {"displayCategoryCode": self.new_cat, "statusName": self.new_status, "items": [{"vendorItemId": 7001}]}
        return {"error": "없음"}

    def stop_sale(self, vid):
        self.stopped.append(vid)
        return {"ok": True}

    def on_sale(self, vid):
        return self.onsale_after


def _saver(box):
    def save(fn):
        fn(box)
    return save


def test_plan_is_read_only_and_names_what_would_stop():
    up = _Up()
    p = CR.plan(_item(_EX), ["coupang:woojoo"], make_up=lambda a: up)
    row = p["markets"]["coupang:woojoo"]
    assert p["ok"] and row["old_sid"] == "16419632846" and row["category_now"] == "77903" and row["category_to"] == "77914"
    assert row["vids"] == ["9001", "9002"] and up.stopped == []


def test_register_writes_old_number_first_then_new():
    box = json.loads(json.dumps(_EX))
    seen = {}

    def fake_register(item_id, markets):
        seen["old_before"] = (box.get("coupang_relist") or {}).get("coupang:woojoo", {}).get("old_sid")
        return {"ok": True, "rows": [{"market": "coupang:woojoo", "success": True, "external_product_id": "16500000001"}]}
    r = CR.register(_item(_EX), ["coupang:woojoo"], save=_saver(box), register_fn=fake_register, make_up=lambda a: _Up())
    assert r["ok"] and seen["old_before"] == "16419632846"         # 등록 **전에** 옛 번호를 적었다
    rel = box["coupang_relist"]["coupang:woojoo"]
    assert rel["new_sid"] == "16500000001" and rel["state"] == "wait_approval" and rel["old_vids"] == ["9001", "9002"]


def _relisted():
    ex = json.loads(json.dumps(_EX))
    ex["coupang_relist"] = {"coupang:woojoo": {"old_sid": "16419632846", "new_sid": "16500000001", "category_to": "77914",
                                               "old_vids": ["9001", "9002"], "state": "wait_approval"}}
    return ex


def test_stop_old_waits_for_new_approval():
    up, box = _Up(new_status="승인대기"), _relisted()
    r = CR.stop_old(_item(box), ["coupang:woojoo"], save=_saver(box), make_up=lambda a: up)
    assert not r["ok"] and up.stopped == [] and "승인완료 뒤에" in r["markets"]["coupang:woojoo"]["why"]


def test_stop_old_refuses_when_new_category_is_wrong():
    up, box = _Up(new_cat=77903), _relisted()
    r = CR.stop_old(_item(box), ["coupang:woojoo"], save=_saver(box), make_up=lambda a: up)
    assert not r["ok"] and up.stopped == [] and "내리지 않아요" in r["markets"]["coupang:woojoo"]["why"]


def test_stop_old_after_approval_stops_every_old_option_and_checks():
    up, box = _Up(), _relisted()
    r = CR.stop_old(_item(box), ["coupang:woojoo"], save=_saver(box), make_up=lambda a: up)
    assert r["ok"] and up.stopped == ["9001", "9002"] and r["markets"]["coupang:woojoo"]["stopped"] == 2
    assert box["coupang_relist"]["coupang:woojoo"]["state"] == "done"
    up2, box2 = _Up(onsale_after=True), _relisted()                # 중지 뒤에도 판매중으로 읽히면 「내렸다」고 안 한다
    r2 = CR.stop_old(_item(box2), ["coupang:woojoo"], save=_saver(box2), make_up=lambda a: up2)
    assert not r2["ok"] and len(r2["markets"]["coupang:woojoo"]["left"]) == 2


def test_register_report_table(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "1650", "account": "gogane", "price": {"line": "x"},
                        "sent": {"name": "3in1 맥세이프 호환 거치대", "sale_price": 30000, "category": "77779", "detail_chars": 900,
                                 "sent_images": {"n": 2, "images": [{"url": "https://a/1.jpg"}, {"url": "https://a/promo.jpg"}]}}},
                       {"market": "smartstore:chezgoga", "product_id": "999", "channel_product_no": "13800000001",
                        "account": "chezgoga", "sent": {"name": "[해외직구] 3in1", "sale_price": 28000}}],
          "images_ko": [{"url": "https://a/promo.jpg", "status": "excluded"}]}
    monkeypatch.setattr(D, "_item", lambda iid: (_item(ex), "u1"))

    class Up:
        def get_product(self, sid):
            return {"statusName": "승인대기", "sellerProductName": "3in1 맥세이프 호환 거치대", "displayCategoryCode": 77779,
                    "items": [{"salePrice": 30000, "originalPrice": 34500}]}
    rep = O.register_report("a0a78ca4", [], make_up=lambda a: Up())
    cp = next(r for r in rep["rows"] if r["market"] == "coupang:gogane")
    nv = next(r for r in rep["rows"] if r["market"] == "smartstore:chezgoga")
    assert cp["status"] == "승인대기" and cp["list_ok"] and cp["category_match"] and cp["excluded_sent"] == ["https://a/promo.jpg"]
    assert nv["no"] == "13800000001"                               # 네이버는 채널 번호만
    assert cp["price_record"] and cp["sent_record"]


def test_successful_upload_queues_register_report(monkeypatch):
    from src.seller_console import views as V
    from src.services import oneshot_ops as O
    got = []
    monkeypatch.setattr(O, "enqueue", lambda row: got.append(row) or True)
    V._queue_register_report("a0a78ca4", {"results": [{"market": "coupang:gogane", "success": True},
                                                      {"market": "smartstore:chezgoga", "success": False}]})
    assert got == [{"op": "register_report", "item_id": "a0a78ca4", "markets": ["coupang:gogane"]}]
    got.clear()
    V._queue_register_report("a0a78ca4", {"results": [{"market": "coupang:gogane", "success": False}]})
    assert got == []


def test_coupang_uploads_reads_old_records_from_url():
    """Y14(10-21): SPORTLINK 쿠팡 16397045086(09-28 기록 — `product_id` 없이 `external_url`만)이 조회 대상에서 빠졌다."""
    from src.services.coupang_detail_refresh import coupang_uploads
    ex = {"uploaded": [{"market": "coupang", "external_url": "https://www.coupang.com/vp/products/16397045086"},
                       {"market": "coupang:woojoo", "product_id": "16419632846"},
                       {"market": "coupang:gogane", "external_url": "https://www.coupang.com/"},          # 번호 없음 — 뺀다
                       {"market": "smartstore:chezgoga", "product_id": "1"}]}
    assert coupang_uploads(ex) == [{"market": "coupang", "account": "", "sid": "16397045086"},
                                   {"market": "coupang:woojoo", "account": "woojoo", "sid": "16419632846"}]


_SPORT = {"uploaded": [{"market": "coupang", "external_url": "https://www.coupang.com/vp/products/16397045086",
                        "market_label": "쿠팡"}]}


class _UpSport(_Up):
    def get_product(self, sid):
        if sid == "16397045086":
            return {"displayCategoryCode": 63978, "statusName": "승인완료", "sellerProductName": "옛 이름",
                    "items": [{"vendorItemId": 8101}, {"vendorItemId": 8102}]}
        if sid == "16500000009":
            return {"displayCategoryCode": 63999, "statusName": self.new_status, "items": [{"vendorItemId": 7009}]}
        return {"error": "없음"}


def test_replace_mode_relists_legacy_record_without_category_target():
    """Y14(오너 10-21 SPORTLINK 쿠팡 고가네): 카테고리는 그대로 · 내용만 바꿔 새로 등록 → 승인 → 옛 16397045086 판매중지.
    예전 기록은 market 「coupang」·번호는 주소에만 — 계정 마켓 「coupang:gogane」의 후보로 보고, 그 계정 키로 조회해 확인한다."""
    up = _UpSport()
    p = CR.plan(_item(_SPORT), ["coupang:gogane"], make_up=lambda a: up, mode="replace")
    row = p["markets"]["coupang:gogane"]
    assert p["ok"] and row["old_sid"] == "16397045086" and row["legacy_record"] and row["mode"] == "replace"
    assert row["vids"] == ["8101", "8102"] and row["category_to"] == "" and up.stopped == []
    # 카테고리 모드(기본)는 바꿀 카테고리가 없으면 멈춘다 — 예전처럼
    assert not CR.plan(_item(_SPORT), ["coupang:gogane"], make_up=lambda a: up)["ok"]
    # 남의 계정 키로는 조회가 실패 → 준비 안 됨
    class _Other(_UpSport):
        def get_product(self, sid):
            return {"error": "권한 없음"}
    assert not CR.plan(_item(_SPORT), ["coupang:woojoo"], make_up=lambda a: _Other(), mode="replace")["ok"]
    # 새 상품 승인 뒤 — 카테고리가 달라도(바꾸기 모드) 옛 상품 옵션 판매중지
    box = json.loads(json.dumps(_SPORT))
    CR.register(_item(_SPORT), ["coupang:gogane"], save=_saver(box), make_up=lambda a: up, mode="replace",
                register_fn=lambda i, m: {"ok": True, "rows": [{"market": "coupang:gogane", "success": True,
                                                                "external_product_id": "16500000009"}]})
    assert box["coupang_relist"]["coupang:gogane"]["mode"] == "replace"
    r = CR.stop_old(_item(box), ["coupang:gogane"], save=_saver(box), make_up=lambda a: up)
    assert r["ok"] and up.stopped == ["8101", "8102"]


def test_owner_exclude_photo_is_not_healed_back(monkeypatch):
    """Y14(오너 10-21 「SPORTLINK 사진 3 제외」): 오너가 뺀 장은 등록에서 빠지고, 자동 되살리기(위험 —)가 풀지 않는다."""
    from src.services import oneshot_ops as O
    from src.services import risk_gate as R
    ex = {"images_ko": [{"idx": 2, "status": "done", "risk_clear": {"img": "u", "words": ["Airpods"]}}],
          "risk_decisions": {"compat:에어팟 호환 표기": {"action": "strip", "names": ["Airpods"], "to": "무선 이어폰"}}}
    assert O._owner_exclude(ex, [("gallery", 2)], "SPORTLINK 사진 3", "u1") == ["gallery 3"]
    e = ex["images_ko"][0]
    assert e["risk_exclude"].startswith(O.OWNER_EXCLUDE_PREFIX) and e["owner_exclude"]["by"] == "u1"
    assert R.heal_retext_excludes(ex) == [] and R.heal_prop_excludes(ex) == [] and e.get("risk_exclude")
    from src.services import image_translate_store as S
    imgs = ["https://img/a.jpg", "https://img/b.jpg", "https://img/c.jpg"]
    assert "https://img/c.jpg" not in S.effective_images(dict(ex, images=imgs), originals=imgs)
