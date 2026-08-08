"""tests/test_v45_shared_extractor.py — 공유 추출기(확장·북마클릿 동일) + 서버 sanity 게이트.

오너: ①초기상태 JSON ②DOM ③부분수집 정직. 가격 sku필드+sanity(통화불일치·KRW<100 거부+경고).
이미지 갤러리(원본해상도·순서·중복제거·1=썸네일). 옵션 sku스펙. 상세=이미지+속성표(데이터만).
리뷰=평점·수+초기JSON 텍스트 상위N(추가 API 금지). 양 경로 동일 추출기 공유(중복 구현 0).
실 Chromium 검증(scripts/_devshot_extractor): A(JSON-LD 20605·재고9 무시·갤러리 dedup·리뷰1) /
B(DOM폴백 61144) / C(부분수집) / D(가격 sanity needs_check).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MF = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


def test_extractor_source_priority():
    # ① 초기상태 JSON(JSON-LD + 전역 상태) ② DOM 폴백 ③ 부분수집
    assert "kgpExtractProduct" in EX
    assert "application/ld+json" in EX and "__NEXT_DATA__" in EX and "_globalStates" in EX
    assert "_domPrice" in EX and "_domImages" in EX
    assert 'partial = !price && images.length === 0' in EX or "partial" in EX
    assert "부분 수집" in EX


def test_price_sanity_and_nonprice():
    assert "_priceSanity" in EX
    assert "KRW: 100" in EX                          # 비상식 하한
    assert "재고" in EX and "리뷰" in EX and "NONPRICE" in EX   # 재고/리뷰 숫자 오인 배제
    assert "needs_check" in EX


def test_images_options_reviews_specs():
    assert "gallery_images" in EX and "detail_images" in EX     # 갤러리/상세 분리
    assert "hiRes" in EX and "uniqPush" in EX                   # 원본해상도 + 중복제거
    assert "_domOptions" in EX and "_domSpecs" in EX            # 옵션·속성표
    assert "aggregateRating" in EX and "reviewBody" in EX       # 리뷰 평점/텍스트(초기 JSON)
    assert "REVIEW_MAX" in EX                                    # 상위 N건


def test_shared_between_extension_and_bookmarklet():
    # 확장: manifest가 추출기를 content_script보다 먼저 로드 → JS 추출기 실행(격리월드 대응)
    # v51: content_scripts[0]은 kgp-net(document_start) → 격리월드 항목(content_script.js 포함) 특정.
    iso = [cs for cs in MF["content_scripts"] if "content_script.js" in cs.get("js", [])][0]
    # v73 STEP2: 감지 순수 모듈 kgp-detect.js가 content_script 앞에 추가 로드(위임 단일 소스).
    # v81 STEP3: 소싱처 매처 kgp-sources.js도 content_script 앞에 로드(팝업과 단일 소스).
    assert iso["js"] == ["kgp-sources.js", "kgp-extractor.js", "kgp-detect.js", "content_script.js"]
    assert iso["js"].index("kgp-extractor.js") < iso["js"].index("content_script.js")
    assert iso["js"].index("kgp-sources.js") < iso["js"].index("content_script.js")
    assert "window.kgpExtractProduct === \"function\"" in CS
    # v86-H: 목록 갈래 억제를 켜려 pageType을 넘기게 됐다(인자 없는 호출 리터럴 → 인자 포함으로).
    #   계약의 뜻은 그대로 — "content_script는 공유 추출기를 호출한다". 인자까지 못박아 완화 아님.
    assert "return window.kgpExtractProduct({ pageType: kgpPageType() });" in CS
    # 북마클릿(v46 STEP4): 가져오기 신뢰성 위해 경량화 — 29KB 인라인 폐기, 페이지 HTML을 서버로 보내
    #   서버가 추출(로직 공유). 여전히 같은 수집 엔드포인트로 전송.
    assert "html:(document.documentElement" in VIEWS         # 페이지 HTML 전송
    assert "/api/v1/collect/extension" in VIEWS
    # 서버가 posted HTML에서 추출(범용 스크래퍼 병합)
    assert "_merge_scraped_into_payload" in API


@pytest.fixture(autouse=True)
def _mem():
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    yield


def test_server_sanity_gate_rejects_low_price():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            # KRW 9(재고/쿠폰 오인) → 서버가 needs_check로 거부 + 경고
            r = c.post("/api/v1/collect/extension", data=json.dumps({
                "url": "https://temu.com/g-1", "title": "책상", "price": "9", "currency": "KRW"}),
                content_type="application/json", headers={"Authorization": "Bearer t"})
            assert r.get_json().get("ok") is True
    items = ch.list_items(seller_ids={"u1"})
    it = [x for x in items if x.get("url") == "https://temu.com/g-1"][0]
    ex = json.loads(it.get("extra_json") or "{}")
    assert ex.get("price_status") == "needs_check"
    assert any("비상식" in w for w in (ex.get("warnings") or []))
