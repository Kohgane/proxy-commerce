"""Y13-G 3·4(오너 2026-10-20) — 등록본 상품명·카테고리 한 번에 고치기(`relist_fix`) · 설명 칸 기본 문장 → AI 초안.

3: 피샹리 쿠팡 77914 · 네이버 50003682 · 상품명 「1인 회전 라운지 소파 의자 거실 디자이너 체어」(재심사 1회).
4: BLACKHOLES 설명 칸 = 10-10 기본 문장(「■ 배송·구매대행 안내」 고정 줄) → 쿠팡·네이버엔 Anthropic 초안을 싣는다(저장값 그대로).
"""
import json

from src.services import relist_fix as RF
from src.seller_console import upload_dispatcher as D

STUB = ("BLACKHOLES 블랙홀 미니 벽등\n\n■ 옵션·상세\n· 색상은 2가지\n\n■ 배송·구매대행 안내\n"
        "· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.\n· 교환·반품은 판매 마켓과 구매대행 정책을 따릅니다.")
AI = {"provider": "anthropic", "text": "우주를 테마로 한 블랙홀 미니 벽등입니다.", "v": 2}


def test_stub_description_is_swapped_for_ai_draft_only():
    out = D.swap_stub_description({"description": STUB, "description_ko": STUB, "detail_auto": AI})
    assert out["description"] == AI["text"] and out["description_ko"] == AI["text"]
    assert out["description_from_ai_draft"] == "anthropic"
    mine = "직접 쓴 상세 — 벽에 거는 무드등입니다."
    assert D.swap_stub_description({"description": mine, "detail_auto": AI})["description"] == mine     # 셀러 글은 그대로
    stub_ai = dict(AI, provider="stub")
    assert D.swap_stub_description({"description": STUB, "detail_auto": stub_ai})["description"] == STUB   # 기본 문장끼리는 안 바꿈
    item = {"extra_json": json.dumps({"detail_auto": AI})}
    assert D.swap_stub_description({"description": STUB}, item)["description"] == AI["text"]           # 저장된 초안에서


class _CUp:
    def __init__(self):
        self.sent = None

    def get_product(self, sid):
        return {"sellerProductId": sid, "sellerProductName": "피샹리 가정 소파 의자 디자이너 거실",
                "displayProductName": "피샹리 가정 소파 의자 디자이너 거실", "generalProductName": "x",
                "displayCategoryCode": 77903, "items": []}

    def live_fix_plan(self, data, *, name="", search_tags=None, brand=None):
        from src.uploaders.coupang_uploader import CoupangUploader
        return CoupangUploader.live_fix_plan(self, data, name=name)

    def modify_product(self, body):
        self.sent = body
        return {"success": True, "market_status": 200}


class _NUp:
    def __init__(self, cat="50003250"):
        self.cat, self.body = cat, None

    def _api_request(self, method, path, data=None):
        if method == "GET" and path.startswith("/v2/products/origin-products/"):
            return {"originProduct": {"statusType": "SALE", "name": "[해외직구] 피샹리 가정용 1인용 소파 … 빈백 소파",
                                      "leafCategoryId": self.cat, "detailAttribute": {"certificationTargetExcludeContent": {}}},
                    "smartstoreChannelProduct": {"channelProductName": "옛 이름", "naverShoppingRegistration": True}}
        if method == "GET" and path.startswith("/v1/categories/"):
            return {"exceptionalCategories": ["KC_CERTIFICATION"]}
        if method == "PUT":
            self.body = data
            return {"originProductNo": 1}
        raise AssertionError(path)

    def _modify_origin(self, no, mutate, channel_mutate=None):
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        return NaverSmartStoreUploader._modify_origin(self, no, mutate, channel_mutate)


def test_relist_fix_changes_name_and_category_on_both_markets(monkeypatch):
    from src.uploaders import naver_kc
    naver_kc._MEM.clear()
    monkeypatch.setattr(naver_kc, "_st", lambda: type("S", (), {"state_get": staticmethod(lambda k: {}),
                                                                "state_set": staticmethod(lambda k, v: None)}))
    name = "1인 회전 라운지 소파 의자 거실 디자이너 체어"
    cu, nu = _CUp(), _NUp()
    c = RF.coupang({"product_id": "16419632846", "account": "woojoo"}, name, "77914", make_up=lambda a: cu)
    assert c["ok"] and cu.sent["displayCategoryCode"] == 77914 and cu.sent["sellerProductName"] == name
    assert cu.sent["requested"] is True and {x["field"] for x in c["changes"]} >= {"상품명", "카테고리"}
    n = RF.naver({"product_id": "13759651461", "account": "chezgoga"}, name, "50003682", make_up=lambda a: nu)
    op = nu.body["originProduct"]
    assert n["ok"] and op["leafCategoryId"] == "50003682" and op["name"] == "[해외직구] " + name
    assert nu.body["smartstoreChannelProduct"]["channelProductName"] == "[해외직구] " + name
    assert op["detailAttribute"]["certificationTargetExcludeContent"]["kcExemptionType"] == "OVERSEAS"   # 새 카테고리 KC면 특례 같이
    assert n["before_category"] == "50003250"
