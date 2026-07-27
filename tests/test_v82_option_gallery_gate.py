"""tests/test_v82_option_gallery_gate.py — v82 STEP1-3: 옵션 정제 · 갤러리 위생 · 페이지타입 게이트.

STEP1 옵션 정제: 폴백 전치(_skusToOptions ②, 축명 소실)가 축 블랙리스트를 우회하던 구멍 봉인 —
  원산지 국가명(タイ)·법인 접미(アーガスコーポレーション)·단독 숫자('1') 배제. receno 색상 정확 일치.
STEP2 갤러리 위생: hiRes 토큰군 [SU][XYLSR]+US/UL/SR — 아마존 _AC_US100_ 등 원본 승격(저해상 근원 제거).
STEP3 페이지타입 게이트: KGPDetect.singleExtractAllowed/singleGateMessage — single 아니면 단일 추출·
  '이 상품 수집하기' 비활성 + 분기 문구. content_script/popup 공용(톱=unknown·검색=list → 저장 불가).

계약(CI 게이트): 소스-컨트랙트(마커 존재) + node 단위(순수 헬퍼 실행). 확장 추출 회귀는 실페이지 하네스
  (scripts/extract_harness.js / tests/test_v70_realpage_harness.py)가 별도 담보 — 본 변경은 5/7 픽스처 불변.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

EXT_DIR = Path("extensions/chrome-collector")
EXTRACTOR = (EXT_DIR / "kgp-extractor.js").read_text(encoding="utf-8")
DETECT = (EXT_DIR / "kgp-detect.js").read_text(encoding="utf-8")
CS = (EXT_DIR / "content_script.js").read_text(encoding="utf-8")
POPUP = (EXT_DIR / "popup.js").read_text(encoding="utf-8")


# ── 소스-컨트랙트(마커 존재) ─────────────────────────────────────────────
def test_step1_option_source_contract():
    assert "function _isBadOptFallbackValue(v)" in EXTRACTOR
    assert "コーポレーション" in EXTRACTOR and "株式会社" in EXTRACTOR   # 법인 접미
    assert "タイ" in EXTRACTOR                                            # 원산지 국가명 값 필터
    assert r"if (/^\d$/.test(v)) return true;" in EXTRACTOR               # 단독 한 자리 숫자
    # 폴백 전치에 값 필터 적용(우회 구멍 봉인).
    assert "!_isBadOptValue(v) && !_isBadOptFallbackValue(v)" in EXTRACTOR


def test_step2_gallery_source_contract():
    assert "[SU][XYLSR]" in EXTRACTOR
    assert "SR|UX|UY|UL|US|CR" in EXTRACTOR   # US/UL/SR 토큰 추가


def test_step3_gate_source_contract():
    assert "function singleExtractAllowed(pt)" in DETECT
    assert "function singleGateMessage(pt)" in DETECT
    assert "singleExtractAllowed: singleExtractAllowed" in DETECT
    # content_script 방어선 + popup 선차단.
    assert "KGPDetect.singleExtractAllowed" in CS and "gated: true" in CS
    assert "kgpSingleGateMessage" in POPUP and "kgpGetPageType" in POPUP
    # v82 정확 문구.
    assert "목록 페이지예요. 타일의 [수집] 버튼이나 벌크바를 쓰세요" in DETECT
    assert "상품 페이지가 아니에요. 상품/목록 페이지에서 수집할 수 있어요" in DETECT


def test_step4_float_card_source_contract():
    assert "function kgpCollectCard(" in CS and "#kgp-collect-card" in CS
    assert "kgpCardPop" in CS and "prefers-reduced-motion" in CS          # Pop in + reduced-motion
    assert "_kgpPlaceCard" in CS and "elementsFromPoint" in CS            # 충돌 회피
    # 부유 UI 우하단 → 우상단(장바구니 가림 근치): bottom 앵커 폐기.
    assert '"bottom:84px"' not in CS and "bottom:96px;z-index" not in CS


# ── node 단위(순수 헬퍼 실행) ────────────────────────────────────────────
_NODE = shutil.which("node")

_UNIT_JS = r"""
const path = require('path');
const EX = require(path.resolve('extensions/chrome-collector/kgp-extractor.js'));
const DET = require(path.resolve('extensions/chrome-collector/kgp-detect.js')).KGPDetect;
const T = EX._test;
const fakeDoc = { querySelector: () => null, querySelectorAll: () => [] };
const out = {
  us100: T.hiRes('https://m.media-amazon.com/images/I/71x._AC_US100_.jpg'),
  ul320: T.hiRes('https://m.media-amazon.com/images/I/71x._AC_UL320_.jpg'),
  sx466: T.hiRes('https://m.media-amazon.com/images/I/71x._AC_SX466_.jpg'),
  receno: T.skusToOptions({ 'カラー': { order: ['ホワイト','グレー','ブラック'], set:{'ホワイト':1,'グレー':1,'ブラック':1}, images:{} } }, []),
  infected: T.skusToOptions({}, [
    { spec: ['ホワイト','アーガスコーポレーション','タイ'] },
    { spec: ['グレー','アーガスコーポレーション','タイ'] },
    { spec: ['ブラック','アーガスコーポレーション','タイ'] },
  ]),
  one: T.skusToOptions({}, [{spec:['レッド']},{spec:['1']},{spec:['ブルー']}]),
  bad1: T.isBadOptValue('1'), bad38: T.isBadOptValue('38'),
  allow_single: DET.singleExtractAllowed('single'),
  allow_list: DET.singleExtractAllowed('list'),
  msg_list: DET.singleGateMessage('list'),
  pt_dp: DET.pageType(fakeDoc, 'https://www.amazon.co.jp/dp/B0TESTXXXX', {cardCount:0}),
  pt_search: DET.pageType(fakeDoc, 'https://www.amazon.co.jp/s?k=steamer', {cardCount:24}),
  pt_top: DET.pageType(fakeDoc, 'https://www.amazon.co.jp/', {cardCount:0}),
};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_v82_units_via_node():
    res = subprocess.run([_NODE, "-e", _UNIT_JS], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    d = json.loads(res.stdout)
    # STEP2: 사이즈/크롭 토큰 원본화.
    assert d["us100"] == "https://m.media-amazon.com/images/I/71x.jpg"
    assert d["ul320"] == "https://m.media-amazon.com/images/I/71x.jpg"
    assert d["sx466"] == "https://m.media-amazon.com/images/I/71x.jpg"   # 기존 유지
    # STEP1: receno 색상 정확 일치.
    assert d["receno"] == [{"name": "カラー", "values": ["ホワイト", "グレー", "ブラック"]}]
    # STEP1: 제조사·원산지 부활 금지, 진짜 색상 보존.
    flat = [v for o in d["infected"] for v in o["values"]]
    assert "アーガスコーポレーション" not in flat and "タイ" not in flat
    assert "ホワイト" in flat and "ブラック" in flat
    # STEP1: 폴백에서 단독 '1' 제거, 사이즈 '38' 보존.
    assert "1" not in [v for o in d["one"] for v in o["values"]]
    assert d["bad1"] is True and d["bad38"] is False
    # STEP3: 게이트.
    assert d["allow_single"] is True and d["allow_list"] is False
    assert d["msg_list"] == "목록 페이지예요. 타일의 [수집] 버튼이나 벌크바를 쓰세요"
    assert d["pt_dp"] == "single" and d["pt_search"] == "list" and d["pt_top"] == "unknown"
