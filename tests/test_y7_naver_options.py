"""Y7(오너 2026-10-08) — 네이버 조합형 옵션 전송.

예전엔 네이버 등록 몸통에 옵션 칸이 없었다 — 「플리츠 미니멀 여성 여름 세트」(SKU 8)도 한 가격·한 재고로 올라갔다.
이제 신규 등록에 `detailAttribute.optionInfo`(optionCombinationGroupNames + optionCombinations)를 싣는다.
값은 `option_ko` 사슬(쿠팡 SKU와 같은 값). 2축까지, 조합 상한 초과는 `option_limit`로 보류. 단일 SKU 상품은 몸통 그대로.
"""
from __future__ import annotations

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

SRC = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
KO = ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트", "로열 블루 상의", "로열 블루 스커트"]


def _pleats(**over):
    """운영 실측 상품(taobao 09-27, SKU 8) — 상의 52,000원 · 스커트 48,005원(원 단위 올림 확인용)."""
    skus = [{"sku_id": f"5{i:03d}", "spec": [v, "均码"], "price": 168.0, "currency": "CNY",
             "stock": 0 if i == 7 else 2000, "sell_price_krw": 52000 if "上衣" in v else 48005}
            for i, v in enumerate(SRC)]
    pd = {"sku": "PLEATS-1", "title_ko": "플리츠 미니멀 여성 여름 세트", "sell_price_krw": 52000, "price": 168,
          "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"],
          "options": [{"name": "颜色分类", "values": list(SRC)}, {"name": "尺码", "values": ["均码"]}],
          "skus": skus}
    pd.update(over)
    return pd


@pytest.fixture
def up(monkeypatch):
    monkeypatch.setenv("NAVER_IMAGE_UPLOAD", "0")
    monkeypatch.delenv("NAVER_OPTION_COMBO_LIMIT", raising=False)
    monkeypatch.setattr(SS, "_template_cache", None, raising=False)
    return SS(account="chezgoga")


def _send(up, monkeypatch, pd):
    from src.channel_sync._channel_bridge import to_collected
    sent = {}
    monkeypatch.setattr(up, "_api_request",
                        lambda m, p, data=None: sent.update({"d": data}) or {"originProductNo": "77"})
    res = up.upload_product(up.prepare_product(to_collected(pd)))
    return res, sent.get("d")


def test_pleats_8_combinations_payload_snapshot(up, monkeypatch):
    res, d = _send(up, monkeypatch, _pleats())
    assert res["success"] is True
    op = d["originProduct"]
    assert op["salePrice"] == 48010                       # 가장 싼 조합(스커트 48,005 → 10원 올림)
    assert op["stockQuantity"] == 999 * 7                 # 조합 재고 합(재고 2000은 상한 999로, 품절 1개는 0)
    assert op["detailAttribute"]["optionInfo"] == {
        "optionCombinationSortType": "CREATE",
        "optionCombinationGroupNames": {"optionGroupName1": "색상", "optionGroupName2": "사이즈"},
        "optionCombinations": [
            {"optionName1": KO[i], "optionName2": "프리사이즈",
             "stockQuantity": 0 if i == 7 else 999,
             "price": 3990 if i % 2 == 0 else 0,           # 상의 52,000 − 48,010
             "sellerManagerCode": f"5{i:03d}", "usable": True}
            for i in range(8)],
        "useStockManagement": True,
        "optionCustom": [], "optionDeliveryAttributes": [],   # 템플릿 승계(조합형과 같이 쓸 수 있는 빈 칸)
    }


def test_option_values_are_the_same_chain_as_coupang(up, monkeypatch):
    """오너 수정값이 이긴다 — 옵션 탭 · 쿠팡 SKU · 네이버 조합이 같은 값."""
    from src.collectors import option_ko as K
    pd = _pleats(option_value_overrides={"宝蓝上衣": "코발트 블루 상의"})
    _res, d = _send(up, monkeypatch, pd)
    names = [c["optionName1"] for c in d["originProduct"]["detailAttribute"]["optionInfo"]["optionCombinations"]]
    assert names[6] == "코발트 블루 상의" == K.spec_ko(pd, ["宝蓝上衣", "均码"])[0]


def test_over_combo_limit_holds_with_reason_code(up, monkeypatch):
    monkeypatch.setenv("NAVER_OPTION_COMBO_LIMIT", "5")
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: pytest.fail("한도 초과인데 전송됨"))
    from src.channel_sync._channel_bridge import to_collected
    res = up.upload_product(up.prepare_product(to_collected(_pleats())))
    assert res["success"] is False and res["held"] is True and res["reason_code"] == "option_limit"
    assert "8개" in res["error"] and "상한 5개" in res["error"]


def test_three_axes_holds_with_option_limit(up, monkeypatch):
    pd = _pleats()
    for k in pd["skus"]:
        k["spec"] = k["spec"] + ["S"]
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: pytest.fail("3축인데 전송됨"))
    from src.channel_sync._channel_bridge import to_collected
    res = up.upload_product(up.prepare_product(to_collected(pd)))
    assert res["reason_code"] == "option_limit" and "2축까지" in res["error"]


def test_prevalidate_and_dispatch_hold_option_limit(monkeypatch):
    """사전검증도 같은 판정(가격 없이 구조만) — 등록 버튼 전에 보인다. 직접 호출 우회 0."""
    monkeypatch.setenv("NAVER_OPTION_COMBO_LIMIT", "5")
    from src.seller_console import upload_dispatcher as UD
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    from src.seller_console import smartstore_routing as SR
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    pv = UD.UploadDispatcher()._prevalidate_market(_pleats(), "smartstore")
    assert pv.ok is False and pv.hold is True and pv.error_code == "option_limit"
    r = UD.UploadDispatcher()._dispatch_one(_pleats(), "smartstore")
    assert r.success is False and r.error_code == "option_limit" and "전송 전에 보류" in r.message


def test_single_sku_product_body_unchanged(up, monkeypatch):
    """SKU 0~1개 — 예전 몸통 그대로(판매가 = 상품 판매가, 재고 999, 조합 칸 없음)."""
    pd = _pleats(skus=[], options=[])
    res, d = _send(up, monkeypatch, pd)
    assert res["success"] is True
    op = d["originProduct"]
    assert op["salePrice"] == 52000 and op["stockQuantity"] == SS.STOCK_QUANTITY
    assert "optionCombinations" not in op["detailAttribute"]["optionInfo"]
    one = _pleats()
    one["skus"] = one["skus"][:1]
    _res, d1 = _send(up, monkeypatch, one)
    assert "optionCombinations" not in d1["originProduct"]["detailAttribute"]["optionInfo"]


@pytest.mark.parametrize("mutate,code", [
    (lambda pd: pd["skus"].append({"sku_id": "x", "spec": ["奇异色上衣", "均码"], "sell_price_krw": 52000}),
     "option_untranslated"),
    (lambda pd: pd.update(option_value_overrides={"蓝色上衣": "블랙 상의"}), "option_duplicate"),
    (lambda pd: pd["skus"][0].pop("sell_price_krw"), "option_price"),
])
def test_other_holds_never_send(up, monkeypatch, mutate, code):
    """못 옮긴 값·겹친 조합·판매가 없는 조합 — 한 가격·원문으로 대신 올리지 않고 보류."""
    pd = _pleats()
    mutate(pd)
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: pytest.fail("보류인데 전송됨"))
    from src.channel_sync._channel_bridge import to_collected
    res = up.upload_product(up.prepare_product(to_collected(pd)))
    assert res["held"] is True and res["reason_code"] == code, res


def test_smartstore_channel_prices_skus_with_smartstore_fees(monkeypatch):
    """SKU별 판매가는 **스마트스토어 수수료**로 낸다(쿠팡 값 재사용 금지) — 식은 `_landed_krw` 하나."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.channel_sync import smartstore_uploader as SU
    markets = []
    monkeypatch.setattr(UploadDispatcher, "_landed_krw",
                        staticmethod(lambda pd, market="": markets.append(market) or (50000.0, "")))
    seen = {}
    monkeypatch.setattr(SU, "run_upload", lambda up, pd, **k: seen.update({"pd": pd}) or {"product_id": "1"})
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    SU.upload(_pleats())
    assert markets and set(markets) == {"smartstore"}
    assert all(k["sell_price_krw"] == 50000 for k in seen["pd"]["skus"])


def test_dispatcher_shows_upload_hold_reason_code(monkeypatch):
    """업로더가 전송 전에 보류하면 결과에 그 사유코드(`option_untranslated`)와 사람 말이 그대로 — 「오류:」로 뭉개지 않는다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.channel_sync import smartstore_uploader as SU
    from src.channel_sync._channel_bridge import ChannelUploadError
    def _raise(pd):
        e = ChannelUploadError("스마트스토어 업로드 실패: 보류: 한국어로 옮기지 못한 옵션 값 1개(奇异色上衣)",
                               lines=["보류: 한국어로 옮기지 못한 옵션 값 1개(奇异色上衣)"], held=True)
        e.reason_code = "option_untranslated"
        raise e
    monkeypatch.setattr(SU, "upload", _raise)
    r = UploadDispatcher()._upload_smartstore({})
    assert r.success is False and r.error_code == "option_untranslated"
    assert r.message.startswith("전송 전에 보류했습니다") and "奇异色上衣" in r.message
