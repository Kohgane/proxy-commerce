"""Y7-F(오너 2026-10-09 13:32 KST, 플리츠 세트 · 셰고가) — 네이버 등록 400 두 칸 + 매핑 누락.

400 본문: invalidInputs = [detailContent NotBlank 「상품 상세 항목을 입력해 주세요」,
                          purchaseQuantityInfo.minPurchaseQuantity NumberMin 「최소구매수량 항목은 2개 이상」].
화면은 「잠시 뒤 다시 시도」(api_error) — 직전 사전검증은 통과였다.

원인(코드로 확인)
1. `detailContent` = 화면 폼의 `description_html or description`(상세 설명 텍스트)뿐 — 그 상품은 비어 있었다. 상세 이미지는 안 실었다.
2. `purchaseQuantityInfo.minPurchaseQuantity: 1`을 늘 실었다(`maxPurchaseQuantityPer1Time`은 문서에 없는 이름).
3. 업로더가 400 본문을 **300자에서 잘라** 넘겼다 — 칸 2개짜리 본문은 약 430자라 JSON을 못 읽어 필드별 매핑이 빈손 → api_error·재시도 안내.
"""
from __future__ import annotations

import json

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

BODY_13_32 = json.dumps({
    "code": "InvalidInput", "message": "요청 값이 올바르지 않습니다.", "timestamp": "2026-10-09T13:32:11.123+09:00",
    "traceId": "0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d^1791531131123^9876543",
    "invalidInputs": [
        {"name": "originProduct.detailContent", "type": "NotBlank", "message": "상품 상세 항목을 입력해 주세요."},
        {"name": "originProduct.detailAttribute.purchaseQuantityInfo.minPurchaseQuantity", "type": "NumberMin",
         "message": "최소구매수량 항목은 2개 이상 입력해 주세요."}]}, ensure_ascii=False)


def _pleats(**over):
    src = ["黑色上衣", "黑色半裙"]
    pd = {"sku": "PLEATS-1", "title_ko": "플리츠 미니멀 여성 여름 세트", "title": "플리츠 미니멀 여성 여름 세트",
          "sell_price_krw": 52000, "price": 168, "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"],
          "category_code": "CLO", "item_id": "it-7f", "naver_category_id": "50000816",
          "options": [{"name": "颜色分类", "values": src}, {"name": "尺码", "values": ["均码"]}],
          "skus": [{"sku_id": str(i), "spec": [v, "均码"], "stock": 5, "sell_price_krw": 52000} for i, v in enumerate(src)]}
    pd.update(over)
    return pd


# ── 1. detailContent = 상세페이지 HTML ────────────────────────────────────────────────────────────

def test_detail_html_has_text_images_and_kc_notice():
    from src.uploaders import naver_detail as ND
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    html = ND.build({"description": "가볍고 시원한 플리츠 세트.\n\n세탁은 손빨래.",
                     "detail_images": ["https://res.cloudinary.com/x/d1.jpg", "https://res.cloudinary.com/x/d2.jpg", "/seller/x"]})
    assert html.count("<img") == 2 and "d1.jpg" in html and "/seller/x" not in html     # 우리 서버 주소는 싣지 않음
    assert "가볍고 시원한 플리츠 세트." in html and html.count("<p") >= 3
    assert PURCHASE_AGENT_NOTICE in html


def test_13_32_item_shape_store_card_text_and_protocol_relative_image():
    """그 상품의 실제 저장값 — 상세 설명은 가게 통계 줄(S2 규칙이 지움) · 상세 이미지는 `//` 주소 + 51×24 가게 아이콘.
    예전 본문 = 빈칸(400). 이제 본문 = 펴진 이미지 1장 + KC 고지."""
    from src.uploaders import naver_detail as ND
    pd = {"description": "츠츠지 할인점\n4.8\n88VIP 긍정 평가율 98%\n평균 12시간 내 발송\n고객센터 평균 답변 시간 10초입니다.",
          "detail_images": ["//img.alicdn.com/imgextra/i1/1116632222/O1CN01SGQy8H1SHiuTtVrP9_!!1116632222-0-shopmanager.jpg_1200x1200q30.jpg_.webp",
                            "https://gtms04.alicdn.com/tps/i4/TB1lLP.HpXXXXb5XpXXaYjxHXXX-51-24.png_.webp"]}
    imgs = ND.detail_images(pd)
    assert len(imgs) == 1 and imgs[0].startswith("https://img.alicdn.com/")
    html = ND.build(pd)
    assert html.count("<img") == 1 and "츠츠지" not in html and "88VIP" not in html


def test_detail_blank_when_no_images_and_no_text():
    from src.uploaders import naver_detail as ND
    assert ND.build({"description": "", "detail_images": []}) == ""
    assert ND.has_content({"detail_images": ["https://a/b.jpg"]}) and ND.has_content({"description": "x"})
    assert ND.body_has_content("") is False
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    assert ND.body_has_content(f"<p>{PURCHASE_AGENT_NOTICE}</p>") is False                # 고지만으로는 본문이 아니다


def test_dispatcher_builds_naver_detail_and_plug_notice_once(monkeypatch):
    """스마트스토어 등록 페이로드 — 상세 이미지·텍스트·KC 고지, 플러그 고지(해당 시)는 맨 위 한 번. 쿠팡은 예전 그대로."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE, PLUG_CN_TITLE
    import src.collectors.voltage_plug as VP
    monkeypatch.setattr(VP, "plug_notice_needed", lambda skus: True)
    pd = _pleats(description="플리츠 세트 상세.", detail_images=["https://res.cloudinary.com/x/d1.jpg"])
    ss, _ = UploadDispatcher._payload_for_market(pd, "smartstore")
    body = ss["description_html"]
    assert body.index(PLUG_CN_TITLE) < body.index("플리츠 세트 상세.") < body.index("d1.jpg")
    assert body.count(PURCHASE_AGENT_NOTICE) == 1                                         # 두 번 붙지 않는다
    cp, _ = UploadDispatcher._payload_for_market(pd, "coupang")
    assert "d1.jpg" not in str(cp.get("description_html") or "")                         # 쿠팡 본문 출처는 그대로(이번 범위 밖)


def test_custom_blocks_win_over_assembled_detail():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = _pleats(description="자동 본문", detail_blocks={"common": [{"type": "text", "content": "셀러가 쓴 본문"}]})
    ss, _ = UploadDispatcher._payload_for_market(pd, "smartstore")
    assert "셀러가 쓴 본문" in ss["description_html"] and "자동 본문" not in ss["description_html"]


# ── 2. purchaseQuantityInfo ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mq,expect", [(None, None), (1, None), ("", None), (2, 2), ("3", 3), (50000, 10000)])
def test_purchase_quantity_only_when_seller_sets_two_or_more(mq, expect):
    p = {"title": "x", "price": 1000, "sku": "S", "description_html": "<p>x</p>", "images": ["https://a/b.jpg"]}
    if mq is not None:
        p["min_purchase_quantity"] = mq
    da = SS(account="chezgoga")._build_product_payload(p)["originProduct"]["detailAttribute"]
    if expect is None:
        assert "purchaseQuantityInfo" not in da                                          # 1을 보내던 경로 제거
    else:
        assert da["purchaseQuantityInfo"] == {"minPurchaseQuantity": expect}
    assert "maxPurchaseQuantityPer1Time" not in json.dumps(da)                            # 문서에 없는 이름


# ── 3. 400 매핑 — 본문 안 자름 · 한 매퍼 · 재시도 안내 없음 ─────────────────────────────────────────

class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text, self.content = status, text, text.encode("utf-8")

    def json(self):
        return json.loads(self.text)


def test_400_body_is_not_truncated_and_maps_both_fields(monkeypatch):
    """13:32 재현 — 본문 약 430자(300자 넘음)여도 칸 2개를 읽는다. 상세 본문 칸은 「상세페이지 꾸미기 →」."""
    assert len(BODY_13_32) > 300
    import src.uploaders.naver_uploader as NU
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "client_id", "id")
    monkeypatch.setattr(up, "client_secret", "sec")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr(NU, "relay_request", lambda *a, **k: _Resp(400, BODY_13_32))
    res = up._api_request("POST", "/v2/products", data={})
    assert res["http_status"] == 400 and res["body"] == BODY_13_32
    from src.uploaders import naver_invalid as NI
    rows = NI.rows(res["body"], "it-7f")
    assert [r["name"] for r in rows] == ["originProduct.detailContent",
                                         "originProduct.detailAttribute.purchaseQuantityInfo.minPurchaseQuantity"]
    assert rows[0]["line"] == "상세 본문 비어 있음 — 상세페이지 꾸미기에서 채우기"
    assert rows[0]["action_label"] == "상세페이지 꾸미기 →" and rows[0]["action_url"] == "/seller/collect/preview/it-7f?tab=detail"


def test_truncated_body_still_yields_field_names():
    from src.uploaders import naver_invalid as NI
    cut = BODY_13_32[:300]
    names = [r["name"] for r in NI.parse(cut)]
    assert "originProduct.detailContent" in names


def test_upload_400_is_naver_invalid_input_with_detail_action(monkeypatch):
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "image_upload_enabled", False)
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setattr(up, "_api_request", lambda m, p, data=None: {
        "error": "네이버 거부 — http_status=400", "http_status": 400, "body": BODY_13_32})
    p = up.prepare_product({"title_ko": "플리츠", "sell_price_krw": 52000, "images": ["https://a/b.jpg"],
                            "description_html": "<p>본문</p>", "item_id": "it-7f", "naver_category_id": "50000816"})
    res = up.upload_product(p)
    assert res["success"] is False and res["reason_code"] == "naver_invalid_input"
    assert "상세 본문 비어 있음 — 상세페이지 꾸미기에서 채우기" in res["error_lines"]
    assert res["action_label"] == "상세페이지 꾸미기 →"
    assert "다시 시도" not in res["error"]


def test_dispatch_result_has_label_and_is_not_retryable(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher, DispatchResult, _RETRY_HINT
    from src.channel_sync import smartstore_uploader as SU
    from src.channel_sync._channel_bridge import ChannelUploadError

    def boom(pd):
        e = ChannelUploadError("스마트스토어 업로드 실패", lines=["상세 본문 비어 있음 — 상세페이지 꾸미기에서 채우기"])
        e.reason_code, e.action_url, e.action_label = ("naver_invalid_input", "/seller/collect/preview/it-7f?tab=detail",
                                                       "상세페이지 꾸미기 →")
        raise e
    monkeypatch.setattr(SU, "upload", boom)
    r = UploadDispatcher()._upload_smartstore({})
    assert r.error_code == "naver_invalid_input" and r.hint != _RETRY_HINT and r.action_label == "상세페이지 꾸미기 →"
    d = DispatchResult(product_url="", results=[r]).to_dict()["results"][0]
    assert d["action_label"] == "상세페이지 꾸미기 →" and d["retryable"] is False


def test_upload_without_detail_is_held_before_naver(monkeypatch):
    """등록 직전 판정 — 본문이 비면 네이버에 보내지 않는다(400 대신 보류 · 사전검증과 같은 사유코드)."""
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "image_upload_enabled", False)
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: pytest.fail("빈 본문으로 네이버에 보냄"))
    p = up.prepare_product({"title_ko": "플리츠", "sell_price_krw": 52000, "images": ["https://a/b.jpg"],
                            "description_html": "", "item_id": "it-7f"})
    res = up.upload_product(p)
    assert res["held"] is True and res["reason_code"] == "naver_required_detailContent"
    assert res["action_label"] == "상세페이지 꾸미기 →"


def test_detail_images_go_to_naver_cdn_and_failed_ones_drop(monkeypatch):
    up = SS(account="chezgoga")

    def fake_upload(urls):
        ok = [u for u in urls if "bad" not in u]
        return {"ok": bool(ok), "urls": [u.replace("https://res.cloudinary.com/x/", "https://shop-phinf.pstatic.net/") for u in ok],
                "skipped": [{"url": u, "reason": "다운로드 실패"} for u in urls if "bad" in u], "reason": ""}
    monkeypatch.setattr(up, "upload_images", fake_upload)
    body = ('<p>본문</p><img src="https://res.cloudinary.com/x/d1.jpg" alt=""><img src="https://res.cloudinary.com/x/bad.jpg" alt="">'
            '<img src="https://shop-phinf.pstatic.net/already.jpg" alt="">')
    out = up._detail_to_cdn(body, "S")
    assert "https://shop-phinf.pstatic.net/d1.jpg" in out and "bad.jpg" not in out and "already.jpg" in out
    assert "res.cloudinary.com" not in out


# ── 4. 사전검증 — 네이버 필수 칸을 먼저 잡는다 ─────────────────────────────────────────────────────

def _pv(monkeypatch, pd):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setattr(NC, "describe", lambda *a, **k: {})
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    import contextlib
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: contextlib.nullcontext())
    return UD.UploadDispatcher().prevalidate(pd, ["smartstore"])[0]


def test_prevalidate_holds_blank_detail_13_32(monkeypatch):
    """13:32 그 모양(상세 설명·상세 이미지 없음) — 예전엔 「통과」 → 등록 400. 이제 사전검증이 보류."""
    pv = _pv(monkeypatch, _pleats())
    assert pv.ok is False and pv.hold is True
    assert pv.error_code == "naver_required_detailContent" and "detail_blank" in pv.fixes
    assert pv.action_url == "/seller/collect/preview/it-7f?tab=detail" and pv.action_label == "상세페이지 꾸미기 →"
    assert pv.message == "사전검증 — 보류: 상세 본문 비어 있음 → 「상세페이지 꾸미기」에서 상세 설명이나 상세 이미지를 채운 후"
    from src.seller_console.views import _pv_dict
    assert _pv_dict(pv)["action_label"] == "상세페이지 꾸미기 →"


def test_prevalidate_passes_with_detail_image_only(monkeypatch):
    pv = _pv(monkeypatch, _pleats(detail_images=["https://res.cloudinary.com/x/d1.jpg"]))
    assert pv.ok is True, pv


def test_prevalidate_required_codes_for_image_and_price(monkeypatch):
    pv = _pv(monkeypatch, _pleats(description="본문", images=[]))
    assert pv.error_code == "naver_required_representativeImage"
    pv = _pv(monkeypatch, _pleats(description="본문", price=0, price_original=0))
    assert pv.error_code == "naver_required_salePrice"


def test_option_price_over_doc_limit_is_held():
    from src.seller_console.upload_dispatcher import naver_required_holds
    pd = _pleats(description="본문")
    pd["skus"][1]["sell_price_krw"] = 2_000_000_000
    codes = [h["code"] for h in naver_required_holds(pd)]
    assert "naver_required_optionPrice" in codes
    assert naver_required_holds(_pleats(description="본문")) == []


# ── 5. 화면 — 서버 글자 그대로 · 400엔 재시도 버튼 없음 · ?tab= ────────────────────────────────────

def test_screens_use_server_label_and_hide_retry_for_400():
    from pathlib import Path
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "renderActionLink(r.action_url, r.action_label)" in cp
    assert "if (r.retryable) _failedMarkets.push(r.market);" in cp                       # 재시도 버튼은 다시 해 볼 만한 실패만
    assert "new URLSearchParams(location.search).get('tab')" in cp
    assert m5.count("r.action_label ? esc(r.action_label)") == 2                         # 사전검증 줄·등록 결과 줄
    assert "'naver_invalid_input', 'category_not_leaf'" not in m5                         # 400을 카테고리로 짐작하던 것 제거
    assert 'data-role="m5-result-details"' in m5                                         # 「사유 2건(아래)」 아래에 목록
