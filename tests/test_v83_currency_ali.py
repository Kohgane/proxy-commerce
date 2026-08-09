"""tests/test_v83_currency_ali.py — v83 STEP1-4: 통화 판정 재설계 · 알리 어댑터 소생 · 수집 위생 · 텔레메트리.

STEP1(P0) 통화: 사다리를 [tier1 명시 통화 필드 → 어댑터 도메인 고정 테이블 → 표시 기호 → html lang 로케일]로
  재설계. 구글 번역(class="translated-ltr")이 lang을 바꿔 7,480円 상품이 KRW로 저장되던 근원 — 번역 DOM이면
  lang 근거를 무효화하고 진단에 translated_dom 표기. 서버는 도메인-통화 정합성 검증(불일치 → 가격 폐기).
STEP2(P0) 알리: *.aliexpress.* 국가 도메인 와일드카드(소싱처 매처 단일 모듈) + DOM sku-item 옵션 어댑터 +
  desc에서 판매자/스토어 블록 제외.
STEP3(P1) v82 STEP1/2 확장: 색상 축 순수 숫자값 제거(tier1·tier2 공통) · 저해상 토큰(__CR..PT0_SX200__) 원본
  승격 및 승격 실패 시 제외 · 제목 카테고리 꼬리(' : Home & Kitchen') 절단(클라+서버) · 라쿠텐 스펙/설명 위생.
STEP4(P2) 텔레메트리: 목록 scanned 카운터 미증가 수정 · 리뷰 있는데 공란이던 rating을 DOM 집계값으로 채움.

계약: 소스-컨트랙트 + node 단위(순수 헬퍼 실행) + 서버 sanitize 단위. 추출 end-to-end 회귀는 실페이지 하네스
  (fixtures/realpages/{rakuten-translated-ko,rakuten-shinogi-ja,ali-ko-sku,amazon-numeric-color-tier1/2})가 담보.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.collectors.collect_sanitize import (
    check_currency_domain,
    domain_currency,
    sanitize_payload,
    sanitize_title,
)

EXT_DIR = Path("extensions/chrome-collector")
EXTRACTOR = (EXT_DIR / "kgp-extractor.js").read_text(encoding="utf-8")
SOURCES = (EXT_DIR / "kgp-sources.js").read_text(encoding="utf-8")
CS = (EXT_DIR / "content_script.js").read_text(encoding="utf-8")
FIX = Path("fixtures/realpages")


# ── 소스-컨트랙트 ────────────────────────────────────────────────────────
def test_step1_currency_ladder_source_contract():
    # 도메인 고정 테이블 + 번역 DOM 판정이 로케일보다 위.
    assert "function _domainCurrency(" in EXTRACTOR
    assert "function _translatedDom(" in EXTRACTOR
    assert "translated-ltr" in EXTRACTOR and "translated-rtl" in EXTRACTOR
    # 로케일 사다리는 삭제가 아니라 최후순위 강등 + 번역 시 lang 무효화(opts.ignoreLang).
    assert "function _localeCurrency(opts)" in EXTRACTOR
    assert "if (opts && opts.ignoreLang) lang = \"\";" in EXTRACTOR
    assert "_localeCurrency({ ignoreLang: translatedDom })" in EXTRACTOR
    # tier1 명시 통화 필드가 최상단(도메인 테이블이 tier1을 덮지 않음).
    assert 'if (currencySrc !== "tier1" && domCur)' in EXTRACTOR
    # 진단·수집 카드 노출.
    assert "currency_source: currencySource, translated_dom: translatedDom" in EXTRACTOR
    assert "번역된 페이지 — 원문 기준으로 저장했어요" in CS


def test_step2_ali_source_contract():
    # 소싱처 매처 단일 모듈에서 국가 도메인 와일드카드(아마존과 동일 규칙).
    # v83 STEP2: TLD 라벨 2~3자로 타이트닝(옛 [a-z][a-z.]*는 amazon.evil.com 류까지 매치).
    assert r"aliexpress\.[a-z]{2,3}(\.[a-z]{2,3})?$" in SOURCES
    assert r"amazon\.[a-z]{2,3}(\.[a-z]{2,3})?$" in SOURCES
    assert r"aliexpress\.(com|us)$" not in SOURCES        # 옛 고정 TLD 잔존 0
    assert r"aliexpress\.(com|us)$" not in CS
    # DOM sku-item 옵션 어댑터 + 판매자 블록 제외.
    assert "function _aliOptions(" in EXTRACTOR
    assert "sku-item--title" in EXTRACTOR and "sku-item--image" in EXTRACTOR
    assert "function _isSellerBlock(" in EXTRACTOR and "_isSellerBlock(el)" in EXTRACTOR


def test_step3_hygiene_source_contract():
    assert "function _dropNumericColorValues(" in EXTRACTOR      # 색상 축 숫자값
    assert "function _isLowResImg(" in EXTRACTOR                 # 승격 실패 저해상 제외
    assert "_AMZ_CAT_TAIL_RE" in EXTRACTOR                       # 제목 카테고리 꼬리(클라)
    assert "_AMZ_CATEGORY_TAIL_RE" in Path("src/collectors/collect_sanitize.py").read_text(encoding="utf-8")
    assert "function _cleanSpecs(" in EXTRACTOR and "function _stripHtmlNoise(" in EXTRACTOR


def test_step4_telemetry_source_contract():
    # 전건 채택(동수)일 때도 scanned 기록(요시다 목록 scanned=0 근원).
    assert "_kgpScannedCount = Math.max(_kgpScannedCount || 0, scanned);" in CS
    assert "if (scanned > cards.length) _kgpScannedCount = scanned;" not in CS
    assert "function _domRating(" in EXTRACTOR


def test_v83_fixtures_present():
    for name in ("rakuten-translated-ko", "rakuten-shinogi-ja", "ali-ko-sku",
                 "amazon-numeric-color-tier1", "amazon-numeric-color-tier2"):
        assert (FIX / f"{name}.html").exists(), name
        spec = json.loads((FIX / f"{name}.expected.json").read_text(encoding="utf-8"))
        assert "합성" in spec["note"], "합성 픽스처는 정직 표기 필수"
    # 번역판 픽스처는 번역 DOM 마크업을 실제로 들고 있어야 재현이 의미 있다.
    assert 'class="translated-ltr"' in (FIX / "rakuten-translated-ko.html").read_text(encoding="utf-8")


# ── 서버측 세이프티(도메인-통화 정합성 · 제목 꼬리) ──────────────────────
def test_domain_currency_table():
    assert domain_currency("https://item.rakuten.co.jp/tsumugi/bag-ai-01/") == "JPY"
    assert domain_currency("https://www.amazon.co.jp/dp/B0X") == "JPY"
    assert domain_currency("https://www.amazon.com/dp/B0X") == "USD"
    assert domain_currency("https://www.amazon.de/dp/B0X") == "EUR"
    assert domain_currency("https://www.temu.com/kr/goods-1.html") == "KRW"
    # 다통화 표시 도메인은 미확정(tier1/기호 위임) — 임의 확정 금지.
    assert domain_currency("https://ko.aliexpress.com/item/1.html") == ""
    assert domain_currency("https://www.temu.com/us/goods-1.html") == ""


def test_server_rejects_domain_currency_mismatch():
    bad = sanitize_payload({"url": "https://item.rakuten.co.jp/tsumugi/bag-ai-01/",
                            "title": "紬 ハンドバッグ", "price": "7480", "currency": "KRW"})
    assert bad["price"] == "" and bad["price_status"] == "needs_check"     # 값 폐기(1/10 오등록 차단)
    assert any("KRW" in w and "JPY" in w for w in bad["warnings"]), bad["warnings"]
    ok = sanitize_payload({"url": "https://item.rakuten.co.jp/tsumugi/bag-ai-01/",
                           "title": "紬 ハンドバッグ", "price": "7480", "currency": "JPY"})
    assert ok["price"] == "7480" and not ok["price_status"]
    # 미확정 도메인(알리)은 통과 — 기존 동작 불변.
    ali = sanitize_payload({"url": "https://ko.aliexpress.com/item/1.html",
                            "title": "블렌더", "price": "9200", "currency": "KRW"})
    assert ali["price"] == "9200"
    assert check_currency_domain("https://www.amazon.com/dp/B0X", "USD") == ""


def test_server_title_category_tail():
    assert sanitize_title("Foldable Storage Box : Home & Kitchen",
                          "https://www.amazon.com/dp/B0CF88RN17") == "Foldable Storage Box"
    assert sanitize_title("Mesh Laundry Bag Set, 5-Pack : Home & Kitchen",
                          "https://www.amazon.com/dp/B0X") == "Mesh Laundry Bag Set, 5-Pack"
    # 카테고리 사전 밖의 콜론(상품명 일부)은 보존 — 임의 절단 금지.
    assert sanitize_title("Case for Galaxy S24: Ultra Slim",
                          "https://www.amazon.com/dp/B0X") == "Case for Galaxy S24: Ultra Slim"
    # 기존 브랜드 접미 제거 회귀 0.
    assert sanitize_title("PORTER TANKER | 吉田カバン", "https://www.yoshidakaban.com/x") == "PORTER TANKER"


# ── node 단위(순수 헬퍼 실행) ────────────────────────────────────────────
_NODE = shutil.which("node")

_UNIT_JS = r"""
const path = require('path');
const T = require(path.resolve('extensions/chrome-collector/kgp-extractor.js'))._test;
global.self = global;
require(path.resolve('extensions/chrome-collector/kgp-sources.js'));
const SRC = global.KGPSources;
const out = {
  // STEP1 도메인 고정 테이블(location 미사용 — 인자 주입).
  dom_rakuten: T.domainCurrency('item.rakuten.co.jp', '/tsumugi/bag/'),
  dom_amazon_jp: T.domainCurrency('www.amazon.co.jp', '/dp/B0X'),
  dom_amazon_com: T.domainCurrency('www.amazon.com', '/dp/B0X'),
  dom_temu_kr: T.domainCurrency('www.temu.com', '/kr/goods-1.html'),
  dom_temu_us: T.domainCurrency('www.temu.com', '/us/goods-1.html'),
  dom_ali: T.domainCurrency('ko.aliexpress.com', '/item/1.html'),
  // STEP1 기호 사전(円 추가 — tsumugi 7,480円).
  yen: T.parsePriceStr('7,480円'),
  won: T.parsePriceStr('₩9,200'),
  // STEP2 소싱처 국가 도메인 와일드카드.
  ali_ko: !!SRC.matchHost('ko.aliexpress.com', {}),
  ali_es: !!SRC.matchHost('es.aliexpress.com', {}),
  ali_best: !!SRC.matchHost('best.aliexpress.com', {}),
  ali_us: !!SRC.matchHost('www.aliexpress.us', {}),
  not_ali: !!SRC.matchHost('aliexpress.evil.com', {}),
  // STEP3 색상 축 숫자값 · 저해상 토큰.
  color_numeric: T.dropNumericColorValues([
    { name: '색상', values: ['1', 'Black', '12'] },
    { name: '사이즈', values: ['38', '40'] },
  ]),
  color_all_numeric: T.dropNumericColorValues([{ name: 'Color', values: ['1', '2'] }]),
  aplus: T.hiRes('https://m.media-amazon.com/images/S/aplus-media/sc/x.__CR0,0,200,225_PT0_SX200__.jpg'),
  us100: T.hiRes('https://m.media-amazon.com/images/I/71x._AC_US100_.jpg'),
  sr: T.hiRes('https://m.media-amazon.com/images/I/71x._AC_SR38,50_.jpg'),
  lowres_left: T.isLowResImg('https://cdn.example.com/img/71x.US100.jpg'),
  lowres_ok: T.isLowResImg('https://m.media-amazon.com/images/I/71x.jpg'),
  // STEP3 스펙·설명 위생.
  specs: T.cleanSpecs([
    { k: 'ブランド', v: '紬工房' },
    { k: '7/31까지! JCB 포인트 증정', v: '엔트리 필수' },
    { k: '공유링크', v: 'https://item.rakuten.co.jp/x/' },
    { k: '배너', v: '.card-promo{font-size:12px;color:#c00}' },
  ]),
  noise: T.stripHtmlNoise('본문 <!-- promo --> 계속 </div ="" =""> 끝'),
};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_v83_units_via_node():
    res = subprocess.run([_NODE, "-e", _UNIT_JS], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    d = json.loads(res.stdout)
    # STEP1 도메인 테이블.
    assert d["dom_rakuten"] == "JPY" and d["dom_amazon_jp"] == "JPY" and d["dom_amazon_com"] == "USD"
    assert d["dom_temu_kr"] == "KRW" and d["dom_temu_us"] == "" and d["dom_ali"] == ""
    assert d["yen"] == {"price": "7480", "currency": "JPY"}
    assert d["won"] == {"price": "9200", "currency": "KRW"}
    # STEP2 와일드카드(악성 유사 도메인은 미매치).
    assert d["ali_ko"] and d["ali_es"] and d["ali_best"] and d["ali_us"]
    assert d["not_ali"] is False
    # STEP3 색상 축 숫자값만 제거, 사이즈 숫자는 보존. 전부 숫자면 축 자체 소멸.
    assert d["color_numeric"] == [{"name": "색상", "values": ["Black"]},
                                  {"name": "사이즈", "values": ["38", "40"]}]
    assert d["color_all_numeric"] == []
    # STEP3 저해상 토큰 원본 승격 + 승격 실패 판정.
    assert d["aplus"] == "https://m.media-amazon.com/images/S/aplus-media/sc/x.jpg"
    assert d["us100"] == "https://m.media-amazon.com/images/I/71x.jpg"
    assert d["sr"] == "https://m.media-amazon.com/images/I/71x.jpg"
    assert d["lowres_left"] is True and d["lowres_ok"] is False
    # STEP3 스펙 위생: 프로모·공유링크·CSS 조각 제거, 실제 속성은 보존.
    assert d["specs"] == [{"k": "ブランド", "v": "紬工房"}]
    assert "<!--" not in d["noise"] and "</div" not in d["noise"] and "본문" in d["noise"]
