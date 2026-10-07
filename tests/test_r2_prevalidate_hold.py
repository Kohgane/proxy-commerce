"""R2(오너 2026-10-01 캡처 23:05) — 사전검증 구멍: 사진 0장인데 「쿠팡 — 통과」, 등록에서야 「이미지 0장 — 등록 불가」.

## 실측(운영 읽기 전용 + 코드)
- 폰 공유로 담은 타오바오 초안 = 원가(예: 199 CNY)는 있고 **이미지 0장 · SKU 0개**(운영 15~36건).
- 서버 사전검증은 `price>0`만 보고, 이미지는 **있을 때만** 접근을 쟀다(0장이면 건너뜀) → 쿠팡 precheck
  참고 사항만 → 「통과」. 등록 단계 `image_norm.screen_images`가 「이미지 0장 — 등록 불가」로 멈췄다.
- 데스크톱도 같은 서버 사전검증을 쓴다(브라우저 쪽 거름 없음) — 편집 화면은 보통 이미지가 있어 안 드러났을 뿐.

## 계약
  1 재료 준비: 판매가>0 · 이미지 ≥1 · (국내 마켓) 옵션 값 한국어 해석 — 하나라도 없으면 **보류**
     문구 「사전검증 — 보류: 이미지 0장·판매가 없음 → PC 확장에서 보강 후」 · 힌트에 「PC 확장에서 보강 필요」
  2 옵션 값 미해석은 「편집 화면에서 옵션 값 번역 후」 · 오너 수정값이 있으면 풀린다
  3 실제 디스패처(쿠팡 자격 있음): 공유 초안 → 보류(통과 0) · 사진 1장 넣으면 재료 게이트는 지난다
  4 /collect/prevalidate JSON에 `hold` · 폰(M5)·데스크톱 화면이 「보류」로 그리고 PC 보강 문구를 결과 옆에 반복
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

FULL_COUPANG = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A01381223",
    "COUPANG_VENDOR_USER_ID": "shanks8", "COUPANG_RETURN_CENTER_CODE": "1000274592",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "7437895", "COUPANG_RETURN_ZIP_CODE": "06236",
    "COUPANG_RETURN_ADDRESS": "서울특별시 강남구 테헤란로 123", "COUPANG_RETURN_CHARGE_NAME": "고가네CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-123-4567",
}
SHARE_DRAFT = {"title": "원목 책상", "title_ko": "원목 책상", "price": "199", "price_original": "199",
               "currency": "CNY", "images": [], "images_effective": [], "skus": [],
               "url": "https://item.taobao.com/item.htm?id=624824402774"}
PC = "PC 확장에서 보강 필요"


def test_brief_sentence_for_no_image_no_price():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_hint, readiness_message
    holds = UploadDispatcher.readiness_holds(dict(SHARE_DRAFT, price="", price_original=""), "coupang")
    assert readiness_message(holds) == "사전검증 — 보류: 이미지 0장·판매가 없음 → PC 확장에서 보강 후"
    assert PC in readiness_hint(holds)


def test_share_draft_with_price_still_holds_on_images():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    holds = UploadDispatcher.readiness_holds(SHARE_DRAFT, "coupang")
    assert readiness_message(holds) == "사전검증 — 보류: 이미지 0장 → PC 확장에서 보강 후"
    assert UploadDispatcher.readiness_holds(dict(SHARE_DRAFT, images=["/seller/static/icon-512.png"],
                                                 images_effective=["/seller/static/icon-512.png"]), "coupang") == []


def test_unresolved_option_values_hold_until_translated():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    p = dict(SHARE_DRAFT, images=["/seller/static/icon-512.png"],
             skus=[{"spec": ["胡桃木色", "120cm"], "price": "199"}, {"spec": ["胡桃木色", "140cm"], "price": "239"}])
    holds = UploadDispatcher.readiness_holds(p, "coupang")
    assert readiness_message(holds).startswith("사전검증 — 보류: 옵션 값 ") and "편집 화면에서 옵션 값 번역 후" in readiness_message(holds)
    n = int(re.search(r"옵션 값 (\d+)개", readiness_message(holds)).group(1))
    p2 = dict(p, option_value_overrides={v: "월넛" for v in ["胡桃木色"]})
    left = UploadDispatcher.readiness_holds(p2, "coupang")
    assert not left or int(re.search(r"옵션 값 (\d+)개", readiness_message(left)).group(1)) < n
    assert UploadDispatcher.readiness_holds(p, "shopify") == []          # 옵션 값 한국어 해석은 국내 마켓만


@pytest.fixture
def coupang_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    for k, v in FULL_COUPANG.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def test_real_dispatcher_holds_the_share_draft(coupang_env):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    [r] = UploadDispatcher().prevalidate(dict(SHARE_DRAFT), ["coupang"])
    assert r.ok is False and r.hold is True and r.error_code == "missing_field"
    assert r.message == "사전검증 — 보류: 이미지 0장 → PC 확장에서 보강 후" and PC in r.hint
    assert r.details and "0장" in r.details[0]
    [r2] = UploadDispatcher().prevalidate(dict(SHARE_DRAFT, images=["/seller/static/icon-512.png"],
                                               images_effective=["/seller/static/icon-512.png"]), ["coupang"])
    assert not r2.hold                                                   # 재료 게이트는 지났다(그 뒤 판정은 기존대로)


def test_route_reports_hold(coupang_env):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-r2"; s["user_role"] = "admin"   # Z6: 서버 env 키(오너 자격)는 공유 사용자만
    d = c.post("/seller/collect/prevalidate", json={"product": dict(SHARE_DRAFT), "markets": ["coupang"]}).get_json()
    [r] = d["results"]
    assert d["all_ok"] is False and r["ok"] is False and r["hold"] is True
    assert r["message"].startswith("사전검증 — 보류:") and PC in r["hint"]


def test_screens_say_hold_and_repeat_the_pc_line():
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "(r.hold ? '보류' : '막힘')" in m5 and 'data-role="m5-hold-pc"' in m5 and "is-hold" in m5
    # M5 후속(오너 2026-10-07): 통과 또는 「그래도 등록」으로 풀리는 보류가 하나도 없으면 등록 닫힘(전송 실패는 잠그지 않음)
    # Y6-C E(2026-10-07) 갱신: 잠긴 버튼 대신 「사전검증부터」 모드 — 통과·보류가 0이면 등록(go) 모드가 아니고,
    #   누르면 다시 사전검증만 한다(등록 0회). 막힌 이유는 버튼 밑 한 줄(m5-go-hint).
    assert "goBtn.dataset.mode = n ? 'go' : 'check';" in m5 and "var n = okMarkets.length + held.length;" in m5
    assert "if (goBtn.dataset.mode !== 'go') { checkBtn.click(); return; }" in m5
    assert "보류된 마켓을 보강하거나 「그래도 등록」을 누르면 등록할 수 있어요." in m5
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="prevalidate-hold">보류' in pv
