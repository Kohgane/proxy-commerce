"""Y11-U(오너 2026-10-16 14:57~14:59 캡처) — Wing 링크 · 쿠팡 정가 · 재심사 중 조회 400.

- 쿠팡 상품 페이지: 4,141,700원 취소선 → 3,601,500원(13%). 판매가 3,601,500 = 마진 계산값(가장 싼 SKU), 정가 4,141,700 =
  예전 정본 규칙 round(판매가×1.15, 100원). 근거 없는 할인 표시는 표시광고 위험 → 정가 = 판매가.
- 상품 수정(재심사) 직후 GET seller-products가 400 {"code":"DEFAULT"} — 오너가 Wing에서 재심사 중 일시 현상으로 확인.
  「확인 못 함」(빨강)이 아니라 「심사 중 — 잠시 후 조회」(회색).
- 「Wing에서 열기」가 Wing 첫 화면으로 떨어진다 — 편집 주소(번호 포함)는 그대로 두고 「번호로 찾기」·「번호 복사」를 붙인다.
  Wing 앱 상품 수정 딥링크는 공개 문서에서 찾지 못했다.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ('쿠팡 거부 — stage=GET /v2/providers/seller_api/apis/api/v1/marketplace/seller-products/16415921785 attempt=1 '
        'http_status=400 body={"code":"DEFAULT","message":"","data":null}')


def _up(get_res):
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    up.get_product = lambda sid: get_res
    return up


def test_review_lock_is_gray_reviewing_not_error():
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    assert CU.is_review_lock(LOCK)
    assert not CU.is_review_lock("쿠팡 거부 — http_status=400 body={\"code\":\"ERROR\",\"message\":\"x\"}")
    assert not CU.is_review_lock("쿠팡 서버 오류 — http_status=500 body={\"code\":\"DEFAULT\"}")
    st = _up({"error": LOCK}).review_status("16415921785")
    assert st["state"] == "reviewing" and st["label"] == "심사 중 — 잠시 후 조회" and st["error"] == "" and "DEFAULT" in st["note"]
    st = _up({"error": "쿠팡 거부 — http_status=404 body={}"}).review_status("1")
    assert st["state"] == "unknown" and st["error"]


def test_reviewing_tone_is_gray_and_remembered():
    from src.seller_console import listing_status as MS
    assert MS.CHIP_TONE["reviewing"] == "wait"
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785", "review": {"state": "approved"}}]}
    assert MS.remember(ex, {"market": "coupang:gogane", "product_id": "16415921785", "state": "reviewing",
                            "label": "심사 중 — 잠시 후 조회", "error": ""})
    assert ex["uploaded"][0]["review"]["state"] == "reviewing"


def test_original_price_equals_sale_price():
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    it = up._sku_item({"itemName": "x", "maximumBuyCount": 3, "externalVendorSku": "s"},
                      {"sell_price_krw": 3601500, "label": "블랙", "sku_id": "1", "image": ""}, {"images": []})
    assert it["salePrice"] == it["originalPrice"] == 3601500


def test_wing_links_and_popup_controls():
    from src.seller_console import listing_status as MS
    rec = {"market": "coupang:gogane", "chip": "쿠팡·고가네", "label": "쿠팡 고가네", "product_id": "16415921785", "at": "",
           "review": {}, "dup_count": 0, "price": {}, "sent": {}}
    row = MS.db_row(rec)
    assert row["manage_url"].endswith("vendorInventoryId=16415921785") and row["manage_label"] == "Wing 상품 수정"
    assert row["wing_search_url"] == "https://wing.coupang.com/vendor-inventory/list?searchKeywords=16415921785"
    t = (ROOT / "src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    assert 'data-role="mst-wing-search"' in t and 'data-role="mst-copy-sid"' in t and 'data-role="mst-reviewing"' in t


def test_action_results_render_at_top_of_row():
    """Y11-T(오너 14:52): 방금 누른 버튼 결과(지금 갱신·상품명 다시 보내기)는 행 맨 위 — 옛 상태 오류 줄보다 앞."""
    t = (ROOT / "src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    i = t.index("function row(r)")
    seg = t[i:t.index("return h + '</div>';", i)]
    assert seg.index("mst-refresh-out") < seg.index("mst-error") and seg.index("mst-name-fix-out") < seg.index("mst-error")
    assert seg.count("mst-refresh-out") == 1 and seg.count("mst-name-fix-out") == 1
