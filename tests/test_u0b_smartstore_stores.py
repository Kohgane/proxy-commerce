"""U0b(오너 2026-10-02 「U0 정정」) — 스마트스토어 두 스토어: 셰고가(chezgoga · 고가네 축) · 고코스모스(gocosmos · 우주대행 축).

  1 스토어별 승인(`SMARTSTORE_<STORE>_APPROVED` → 없으면 전체 플래그) · 미승인은 **보류**(「커머스API 미승인 — 신청 대기」, 전송 0)
  2 스토어별 키 `NAVER_<STORE>_CLIENT_ID/SECRET`(코드 규약 그대로 — 브리프의 SMARTSTORE_<STORE>_ 이름은 쓰지 않음)
  3 카테고리·상품명으로 자동 배정(근거 없거나 동점이면 비움 — 오너가 고름) · 니치·고단가 기준은 표에 값이 있을 때만
  4 한도 1,000(판매중·판매대기·품절) — 커머스 API `products/search totalElements`로만 셈, 못 세면 「조회 불가」, 꽉 차면 보류
  5 마켓 선택 = 사업자 축(고가네: 쿠팡 고가네 + 스스 셰고가 / 우주대행: 쿠팡 우주대행 + 스스 고코스모스) ·
    기본 체크 = 키 있는 쿠팡 둘 + 승인된 배정 스토어 하나 · 비관리자는 한 줄씩 그대로
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.seller_console import smartstore_routing as SR


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in ("SMARTSTORE_APPROVED", "SMARTSTORE_CHEZGOGA_APPROVED", "SMARTSTORE_GOCOSMOS_APPROVED"):
        monkeypatch.delenv(k, raising=False)
    SR.reset_cache()
    yield
    SR.reset_cache()


def test_approval_is_per_store_with_the_old_flag_as_fallback(monkeypatch):
    assert not SR.approved("chezgoga") and not SR.approved("gocosmos")
    monkeypatch.setenv("SMARTSTORE_GOCOSMOS_APPROVED", "1")
    assert SR.approved("gocosmos") and not SR.approved("chezgoga")
    monkeypatch.setenv("SMARTSTORE_APPROVED", "1")
    assert SR.approved("chezgoga")
    monkeypatch.setenv("SMARTSTORE_CHEZGOGA_APPROVED", "0")                 # 스토어 플래그가 이긴다
    assert not SR.approved("chezgoga")


def test_auto_assignment_by_category_and_title():
    assert SR.assign_store({"title_ko": "알루미늄 기계식 키보드 데스크 매트", "category_code": "ELC"})["store"] == "chezgoga"
    assert SR.assign_store({"title_ko": "스테인리스 냄비 주방 세트", "category_code": "HOM"})["store"] == "gocosmos"
    assert SR.assign_store({"title_ko": "강아지 고양이 펫 쿠션"})["store"] == "gocosmos"
    none = SR.assign_store({"title_ko": "무언가 상품"})
    assert none["store"] == "" and "직접 골라" in none["why"]
    assert SR.price_hold({"sell_price_krw": 1000}) == ""                     # 기준 없음(볼트에 수치 결정 없음) — 꺼짐


def test_limit_counts_only_from_the_api(monkeypatch):
    assert SR.limit_state("gocosmos")["text"].endswith("조회 불가(커머스API 미승인)")
    monkeypatch.setenv("SMARTSTORE_GOCOSMOS_APPROVED", "1")
    st = SR.limit_state("gocosmos", fetch=lambda s: 1000)
    assert st["full"] and st["text"] == "고코스모스 1,000/1,000"
    SR.reset_cache()
    assert SR.limit_state("gocosmos", fetch=lambda s: None)["text"].endswith("조회 불가(조회 실패)")


def test_count_products_reads_total_elements(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    seen = []
    monkeypatch.setattr(N, "_api_request", lambda self, m, p, data=None: seen.append((m, p, data)) or {"totalElements": 778})
    assert N(account="gocosmos").count_products() == 778
    assert seen[0][:2] == ("POST", "/v1/products/search") and seen[0][2]["productStatusTypes"] == ["SALE", "WAIT", "OUTOFSTOCK"]
    monkeypatch.setattr(N, "_api_request", lambda self, m, p, data=None: {"error": "401"})
    assert N(account="gocosmos").count_products() is None


def test_unapproved_store_is_held_and_nothing_is_sent(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    called = []
    monkeypatch.setattr(UploadDispatcher, "_upload_smartstore", lambda self, pd: called.append(pd))
    pd = {"title": "냄비", "title_ko": "냄비", "price": "10", "images": ["/x.png"], "sell_price_krw": 30000}
    r = UploadDispatcher().prevalidate(pd, ["smartstore:gocosmos"])[0]
    assert r.market == "smartstore:gocosmos" and r.ok is False and r.hold is True
    assert r.message == "고코스모스 — 커머스API 미승인 — 신청 대기"
    d = UploadDispatcher().dispatch(pd, ["smartstore:gocosmos"]).to_dict()["results"][0]
    assert d["success"] is False and "보류" in d["message"] and not called
    assert d["market_label"] == "스마트스토어 — 고코스모스"


def test_full_store_is_held(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setenv("SMARTSTORE_CHEZGOGA_APPROVED", "1")
    monkeypatch.setattr(SR, "store_count", lambda s, fetch=None: 1000)
    r = UploadDispatcher().prevalidate({"title": "키보드", "price": "10", "images": ["/x.png"]}, ["smartstore:chezgoga"])[0]
    assert r.hold is True and r.error_code == "smartstore_limit_full" and "셰고가 1,000/1,000" in r.message


def test_store_keys_are_used_for_that_store(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    from src.seller_console.market_cred_view import naver_account
    from src.channel_sync import smartstore_uploader as B
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_ID", "cos-id")
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_SECRET", "cos-sec")
    seen = []
    monkeypatch.setattr(N, "upload_product", lambda self, p: seen.append((self.account, self.client_id)) or
                        {"success": True, "product_id": "1"})
    with naver_account("gocosmos"):
        B.upload({"title": "냄비", "title_ko": "냄비", "sell_price_krw": 30000, "price": 30000, "images": ["/x.png"],
                  "sku": "1"})
    assert seen and seen[0] == ("gocosmos", "cos-id")


def test_picker_groups_by_business_with_defaults(monkeypatch):
    import src.seller_console.views as V
    for k, v in {"COUPANG_GOGANE_ACCESS_KEY": "g", "COUPANG_GOGANE_SECRET_KEY": "g", "COUPANG_GOGANE_VENDOR_ID": "A01381223",
                 "COUPANG_WOOJOO_ACCESS_KEY": "w", "COUPANG_WOOJOO_SECRET_KEY": "w", "COUPANG_WOOJOO_VENDOR_ID": "A01504840",
                 "NAVER_CHEZGOGA_CLIENT_ID": "c", "NAVER_CHEZGOGA_CLIENT_SECRET": "c",
                 "NAVER_GOCOSMOS_CLIENT_ID": "o", "NAVER_GOCOSMOS_CLIENT_SECRET": "o",
                 "SMARTSTORE_GOCOSMOS_APPROVED": "1"}.items():
        monkeypatch.setenv(k, v)
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(SR, "store_count", lambda s, fetch=None: 778)
    base = [{"code": m, "label": m, "connected": True, "checked": m == "coupang"}
            for m in ("coupang", "smartstore", "elevenst", "shopify", "woocommerce")]
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert [m["code"] for m in V._with_coupang_accounts(base, {"title_ko": "스테인리스 냄비 주방"})] == [m["code"] for m in base]
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    rows = V._with_coupang_accounts(base, {"title_ko": "스테인리스 냄비 주방", "category_code": "HOM"})
    assert [m["code"] for m in rows[:4]] == ["coupang:gogane", "smartstore:chezgoga", "coupang:woojoo", "smartstore:gocosmos"]
    assert [m["group_label"] for m in rows[:4]] == ["고가네", "고가네", "우주대행", "우주대행"]
    by = {m["code"]: m for m in rows}
    assert by["coupang:gogane"]["checked"] and by["coupang:woojoo"]["checked"]                 # 쿠팡 둘 다
    assert by["smartstore:gocosmos"]["checked"] and "자동 배정" in by["smartstore:gocosmos"]["note"]
    assert by["smartstore:gocosmos"]["limit_text"] == "고코스모스 778/1,000"
    assert not by["smartstore:chezgoga"]["checked"] and by["smartstore:chezgoga"]["pending"]     # 미승인 — 체크 안 함
    assert "커머스API 미승인" in by["smartstore:chezgoga"]["note"]
    assert [m["code"] for m in rows[4:]] == ["elevenst", "shopify", "woocommerce"]


def test_screens_render_groups():
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="m5-group"' in m5 and 'data-role="m5-market-limit"' in m5
    assert 'data-role="ss-pending"' in pv and "^smartstore:" in pv
