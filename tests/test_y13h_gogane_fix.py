"""Y13-H 2(10-20 표 정리 중 발견) — 피샹리 고가네 쿠팡 16421222858: 카테고리 77903(오너 결정 77914 아님) · 상세 = 상품명 26자.

원인 ① 「등록본 고치기」가 상품 기록에 네이버 카테고리만 남기고 쿠팡 카테고리는 안 남겼다 → 다음 계정 등록은 쿠팡 예측(77903).
원인 ② 설명 칸이 가게 배너뿐(마켓 규칙이 다 뺌) → 쿠팡 빌더는 자동 초안을 따로 안 봐서 `_build_contents`가 상품명으로 채웠다.
"""
import json

from src.seller_console import upload_dispatcher as D
from src.services import relist_fix as RF

BANNER = "菲尚丽家旗舰店\n5.0\n好评率98%\n物流好评率98%\n客服满意度93%"
AI = {"provider": "anthropic", "text": "혼자만의 휴식이 필요한 공간에 편안하게 자리 잡는 1인용 라운지 소파입니다."}


def test_empty_description_after_market_rules_uses_ai_draft():
    out = D.fill_empty_description({"description": "", "detail_auto": AI})
    assert out["description"].startswith("혼자만의 휴식") and out["description_from_ai_draft"] == "anthropic"
    item = {"extra_json": json.dumps({"detail_auto": AI})}
    assert D.fill_empty_description({"description": ""}, item)["description"].startswith("혼자만의")   # 저장된 초안에서
    mine = {"description": "직접 쓴 상세입니다.", "detail_auto": AI}
    assert D.fill_empty_description(mine)["description"] == "직접 쓴 상세입니다."                   # 셀러 글은 그대로
    html = {"description": "", "description_html": "<p>꾸민 본문</p>", "detail_auto": AI}
    assert D.fill_empty_description(html)["description"] == ""                                     # HTML 본문은 손대지 않음
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE as N
    kc = D.fill_empty_description({"description": N, "detail_auto": AI})["description"]               # 고지만 남은 설명
    assert kc.startswith(N) and "혼자만의 휴식" in kc


def test_coupang_body_gets_draft_not_title_when_desc_is_shop_banner(monkeypatch):
    from src.channel_sync._channel_bridge import to_collected
    from src.channel_sync.coupang_uploader import prepared_input
    from src.uploaders.coupang_uploader import CoupangUploader
    item = {"id": "x", "extra_json": json.dumps({"detail_auto": AI})}
    pd = D.build_dispatch_payload({"title": "1인 회전 라운지 소파 의자 거실 디자이너 체어", "description": BANNER,
                                   "sell_price_krw": 588900}, item)          # 갱신 경로처럼 몸통엔 초안 없음 · 저장본에만
    up = CoupangUploader.__new__(CoupangUploader)
    monkeypatch.setattr(CoupangUploader, "detail_image_urls", lambda self, p: [])
    prepared = up.prepare_product(to_collected(prepared_input(pd)))
    body = up._build_contents(prepared)[0]["contentDetails"][0]["content"]
    assert "혼자만의 휴식" in body and "菲尚丽" not in body


def test_owner_pinned_coupang_category_beats_prediction():
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    up.predict_category = lambda title, description="": "77903"
    assert up.category_for({"title": "라운지 소파", "coupang_category_id": "77914"}) == ("77914", "owner", "")
    assert up.category_for({"title": "라운지 소파"})[0] == "77903"
    from src.channel_sync._channel_bridge import to_collected
    from src.seller_console.product_builder import build_product
    p = build_product({"id": "x", "title": "t", "extra_json": json.dumps({"coupang_category_id": "77914"})},
                      edits={}, seller_id="u")
    assert up.prepare_product(to_collected(p))["coupang_category_id"] == "77914"                  # 빌더→다리→업로더까지 안 떨어진다


def test_relist_fix_saves_coupang_category_for_next_registrations(monkeypatch):
    saved = {}

    def save(fn):
        fresh = {"uploaded": [{"market": "coupang:woojoo"}]}
        fn(fresh)
        saved.update(fresh)

    monkeypatch.setattr(RF, "coupang", lambda rec, name, cat: {"ok": True, "changes": []})
    item = {"id": "i", "extra_json": json.dumps({"uploaded": [{"market": "coupang:woojoo", "product_id": "1",
                                                               "account": "woojoo"}]})}
    RF.run(item, ["coupang:woojoo"], name="새 이름", coupang_category="77914", save=save)
    assert saved["coupang_category_id"] == "77914" and saved["coupang_name"] == "새 이름"


def test_coupang_inspect_reads_only(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    ex = {"uploaded": [{"market": "coupang:gogane", "account": "gogane", "product_id": "16421222858"}]}
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": iid, "extra_json": json.dumps(ex)}, "u"))
    calls = []

    class _Up:
        def get_product(self, sid):
            calls.append(sid)
            return {"sellerProductName": "1인 회전 라운지 소파", "displayCategoryCode": 77903, "brand": "",
                    "items": [{"itemName": "아이보리", "originalPrice": 677300, "salePrice": 588900, "emptyBarcode": True,
                               "attributes": [{"attributeTypeName": "수량", "attributeValueName": "1개"}]}]}

        def modify_product(self, body):                          # 부르면 안 된다
            raise AssertionError("읽기 전용")
    out = O.coupang_inspect("i", [], make_up=lambda a: _Up())
    assert out["ok"] and calls == ["16421222858"]
    it = out["rows"][0]["items"][0]
    assert out["rows"][0]["category"] == "77903" and it["originalPrice"] == 677300 and it["attributes"] == [["수량", "1개"]]
    assert "coupang_inspect" in O.OPS
