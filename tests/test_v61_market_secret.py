"""tests/test_v61_market_secret.py — v61 STEP0(마스킹)+STEP1(WC406)+STEP3(SS게이트)+STEP4(11st진단).

STEP0: 자격증명 마스킹 유틸(ck_****d4a7) — URL 쿼리·Authorization 헤더·리터럴.
STEP1: WooCommerce 자격증명=Basic Auth 헤더(쿼리 아님)+브라우저 UA+빈 sku 제거+에러 마스킹.
STEP3: 스마트스토어 커머스솔루션 승인 전 업로드 차단(심사중) + 승인 플래그.
STEP4: 11번가 응답 코드·메시지 원문(마스킹)으로 '등록 실패: 등록 실패' 동어반복 제거.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


# ── STEP0 마스킹 ──
def test_mask_value_format():
    from src.utils.secret_mask import mask_value
    assert mask_value("ck_1234567890abcd4a7") == "ck_****d4a7"
    assert mask_value("cs_secretlongvalue9999") == "cs_****9999"
    assert mask_value("short") == "****"


def test_mask_text_url_and_header():
    from src.utils.secret_mask import mask_text, mask_url
    u = mask_url("https://s/wp-json?consumer_key=ck_1234567890abcd4a7&consumer_secret=cs_abcdef9999")
    assert "ck_****d4a7" in u and "cs_****9999" in u
    assert "1234567890abcd" not in u and "abcdef9999" not in u
    h = mask_text("Authorization: Basic Y2tfMTIzNDU2Nzg5MGFiY2RlZg==")
    assert "Y2tfMTIzNDU2Nzg5MGFiY2RlZg==" not in h        # base64 값 노출 0
    # 일반 단어 오탐 없음
    assert mask_text("the product key feature") == "the product key feature"


def test_mask_literal_secret_anywhere():
    from src.utils.secret_mask import mask_text
    out = mask_text("406 error body ...cs_realsecret123456... trailing", secrets=["cs_realsecret123456"])
    assert "cs_realsecret123456" not in out and "cs_****3456" in out


# ── STEP1 WC ──
def test_wc_uses_basic_auth_and_browser_ua():
    import src.vendors.woocommerce_client as wc

    class _Resp:
        status_code = 200
        text = "[]"
        def json(self):
            return []
        def raise_for_status(self):
            pass
    with patch("requests.request", return_value=_Resp()) as mr, \
         patch.object(wc, "_woo_ck", return_value="ck_test1234"), \
         patch.object(wc, "_woo_cs", return_value="cs_test1234"):
        wc._request_with_retry("GET", "https://shop/wp-json/wc/v3/products", params={"sku": "A1", "blank": ""})
        kw = mr.call_args[1]
        assert kw["auth"] == ("ck_test1234", "cs_test1234")
        assert "consumer_key" not in kw["params"]
        assert kw["params"] == {"sku": "A1"}               # 빈 blank 제거
        assert "Mozilla" in kw["headers"]["User-Agent"]


def test_wc_find_by_sku_empty_returns_none():
    import src.vendors.woocommerce_client as wc
    with patch("requests.request") as mr:
        assert wc._find_by_sku("") is None                 # 빈 sku → 조회 안 함(오매칭 방지)
        mr.assert_not_called()


# ── STEP3 스마트스토어 게이트 ──
def test_smartstore_blocked_until_approved(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher, smartstore_approved
    monkeypatch.delenv("SMARTSTORE_APPROVED", raising=False)
    assert smartstore_approved() is False
    d = UploadDispatcher()
    r = d._prevalidate_market({"title": "x", "price": "1000"}, "smartstore")
    assert r.ok is False and r.error_code == "smartstore_pending_review"
    assert "심사중" in r.message
    # 승인 플래그 켜면 통과(게이트 해제 — 이후 env 검증 단계로)
    monkeypatch.setenv("SMARTSTORE_APPROVED", "1")
    assert smartstore_approved() is True
    r2 = d._prevalidate_market({"title": "x", "price": "1000"}, "smartstore")
    assert r2.error_code != "smartstore_pending_review"    # 게이트 통과(이후 env 검증)


def test_smartstore_pending_badge_in_template():
    tpl = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "m.pending" in tpl and "심사중" in tpl and "disabled" in tpl


# ── STEP4 11st 진단 ──
def test_elevenst_no_tautology_error():
    # 11번가 파서가 코드+메시지 원문(마스킹)으로 구체화 — '등록 실패: 등록 실패' 동어반복 제거.
    src = Path("src/uploaders/elevenst_uploader.py").read_text(encoding="utf-8")
    assert 'f"[{code}] {raw_msg}"' in src                  # 코드+메시지 구체화
    assert "동어반복 금지" in src
    assert "mask_text" in src                              # 마스킹 적용
    assert '"message": message' in src and '"code": code' in src
