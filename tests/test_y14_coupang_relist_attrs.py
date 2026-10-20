"""Y14(오너 10-20 순찰 2+3) — 쿠팡 수정 PUT의 빈 바코드 칸 · 카테고리 바꿀 때 옵션 속성 · 같은 PUT에 상세.

실측: 피샹리 우주대행 16419632846 「등록본 고치기」(10-20 10:40) PUT은 카테고리 77914를 실었는데 응답이
SUCCESS + 「[GTIN 속성이 유효하지 않습니다. 상품 옵션 속성을 확인해 주세요.]」 — 상품명만 바뀌고 카테고리는 77903 그대로.
조회 원문 옵션 속성에 「Global Trade Item Number」·「Manufacturer Part Number」·「Parent Manufacturer Part Number」 빈 칸이
붙어 오고, 수정 PUT은 그걸 그대로 돌려보냈다. 등록 빌더(`attr_safe`)는 「gtin」 낱말만 걸러 이 이름들을 못 봤다.
"""
from src.services import relist_fix as RF
from src.uploaders.coupang_uploader import CoupangUploader as CU

_ATTRS = [
    {"attributeTypeName": "프레임재질", "attributeValueName": ""},
    {"attributeTypeName": "색상", "attributeValueName": "플란넬 아이보리+블랙", "exposed": "EXPOSED"},
    {"attributeTypeName": "Global Trade Item Number", "attributeValueName": ""},
    {"attributeTypeName": "Parent Manufacturer Part Number", "attributeValueName": ""},
    {"attributeTypeName": "Manufacturer Part Number", "attributeValueName": ""},
    {"attributeTypeName": "색상계열", "attributeValueName": ""},
]


def _live():
    return {"sellerProductId": 16419632846, "sellerProductName": "1인 회전 라운지 소파 의자 거실 디자이너 체어",
            "displayCategoryCode": 77903, "brand": "GENERIC",
            "items": [{"itemName": "플란넬 아이보리+블랙", "attributes": [dict(a) for a in _ATTRS],
                       "contents": [{"contentsType": "TEXT", "contentDetails": [{"content": "1인 회전 라운지 소파", "detailType": "TEXT"}]}]}]}


def test_shared_barcode_filter_registration_and_edit_put():
    """등록 빌더와 수정 PUT이 같은 판정 — 이름 셋 다 바코드 계열 · 수정 PUT은 **빈** 칸만 뺀다."""
    for n in ("GTIN", "Global Trade Item Number", "Manufacturer Part Number", "Parent Manufacturer Part Number"):
        assert CU.is_barcode_attr(n)
    assert not CU.is_barcode_attr("색상") and not CU.is_barcode_attr("제조사")
    # 등록 빌더 — 같은 판정으로 안 보냄
    names = [a["attributeTypeName"] for a in CU.attr_safe(_ATTRS, "소파")]
    assert not [n for n in names if CU.is_barcode_attr(n)]
    # 수정 PUT(`live_fix_plan`) — 빈 바코드 칸 3개 빠지고 나머지는 그대로 · 바뀜 목록엔 안 들어간다(그것만으론 PUT 안 함)
    plan = CU.live_fix_plan(CU.__new__(CU), _live())
    left = [a["attributeTypeName"] for a in plan["body"]["items"][0]["attributes"]]
    assert plan["dropped_barcode"] == 3 and left == ["프레임재질", "색상", "색상계열"] and plan["changes"] == []
    # 값이 있는 바코드 칸은 손대지 않는다
    body = {"items": [{"attributes": [{"attributeTypeName": "Global Trade Item Number", "attributeValueName": "880123"}]}]}
    assert CU.strip_empty_barcode_attrs(body) == 0 and len(body["items"][0]["attributes"]) == 1


class _Up(CU):
    def __init__(self):
        self.sent = None

    def get_product(self, sid):
        return _live()

    def get_category_attribute_schema(self, code):
        assert code == "77914"
        return [{"attributeTypeName": "색상", "required": True, "exposed": "EXPOSED"},
                {"attributeTypeName": "수량", "required": True, "exposed": "NONE"},
                {"attributeTypeName": "소파 종류", "required": False}]

    def modify_product(self, body):
        self.sent = body
        return {"success": True, "market_status": 200, "body": '{"code":"SUCCESS"}'}


def test_category_change_reshapes_attrs_and_carries_detail(monkeypatch):
    up = _Up()
    from src.services import coupang_detail_refresh as CDR
    draft = [{"contentsType": "TEXT", "contentDetails": [{"content": "■ 상품 소개\n회전 라운지 소파 …" * 5, "detailType": "TEXT"}]}]
    monkeypatch.setattr(CDR, "target", lambda item, u, seller_id="": {"ready": True, "contents": draft})
    r = RF.coupang({"product_id": "16421222858", "account": "gogane"}, "1인 회전 라운지 소파 의자 거실 디자이너 체어", "77914",
                   make_up=lambda a: up, item={"id": "6f9c7ddf"}, detail=True)
    assert r["ok"] and up.sent["displayCategoryCode"] == 77914
    attrs = {a["attributeTypeName"]: a["attributeValueName"] for a in up.sent["items"][0]["attributes"]}
    # 옛 카테고리 빈 칸(프레임재질·색상계열)·빈 바코드 칸은 빠지고, 값 있는 색상은 남고, 새 메타 필수(수량)는 채워진다
    assert attrs.get("색상") == "플란넬 아이보리+블랙" and "수량" in attrs
    assert not ({"프레임재질", "색상계열"} & set(attrs)) and not [n for n in attrs if CU.is_barcode_attr(n)]
    assert up.sent["items"][0]["contents"] == draft            # 같은 PUT에 상세(AI 초안)
    fields = {c["field"] for c in r["changes"]}
    assert {"카테고리", "옵션 속성(새 카테고리 메타)", "상세"} <= fields and r["dropped_barcode"] == 3


def test_detail_not_ready_does_not_send(monkeypatch):
    up = _Up()
    from src.services import coupang_detail_refresh as CDR
    monkeypatch.setattr(CDR, "target", lambda item, u, seller_id="": {"ready": False, "failed": 2, "why": "번역 대기"})
    r = RF.coupang({"product_id": "1", "account": "gogane"}, "x", "77914", make_up=lambda a: up, item={"id": "i"}, detail=True)
    assert not r["ok"] and up.sent is None and "상세가 아직 준비 안 됨" in r["error"]


def test_category_not_applied_is_reported_not_success():
    """Y14(10-20 19:40 피샹리 2계정): PUT SUCCESS인데 다시 조회하면 77903 그대로 — 「미반영」을 적는다(가짜 성공 금지)."""
    up = _Up()                                   # get_product가 늘 77903을 돌려준다(쿠팡이 카테고리를 무시한 상태)
    r = RF.coupang({"product_id": "16419632846", "account": "woojoo"}, "1인 회전 라운지 소파 의자 거실 디자이너 체어", "77914",
                   make_up=lambda a: up)
    assert r["ok"] and r["category_after"] == "77903" and r["unapplied"] == ["카테고리"]
    assert "Wing에서 카테고리를 직접" in r["warning"]

    class _Applied(_Up):
        def get_product(self, sid):
            d = _live()
            if self.sent:
                d["displayCategoryCode"] = 77914
            return d
    up2 = _Applied()
    r2 = RF.coupang({"product_id": "1", "account": "woojoo"}, "x", "77914", make_up=lambda a: up2)
    assert r2["category_after"] == "77914" and "unapplied" not in r2
