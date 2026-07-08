"""tests/test_v46_isoworld_extract.py — v46 STEP3: 확장 격리월드 대응(인라인 <script> 텍스트) + sku/이미지/리뷰.

근본: Chrome content script는 **격리 월드**라 페이지의 live window.rawData를 못 읽는다. 수리:
인라인 <script> 텍스트에서 'window.rawData = {...}' 류 초기 상태를 균형 매칭 파싱(DOM 텍스트=격리월드
접근 가능). 확장·북마클릿 동일 코드. walker 강화: sku 배열→옵션·sku별 가격·메인가(첫 sku),
이미지 배열(배열 키가 이미지류)→갤러리, 평점/리뷰수 키 휴리스틱.

실 Chromium 검증(scripts): live window.rawData 없이 인라인 <script>에서 20605 KRW·재고9 무시·
갤러리·리뷰·평점 추출. JSON-LD/DOM폴백/부분수집/sanity 4케이스 무회귀.
"""
from __future__ import annotations

from pathlib import Path

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")


def test_isolated_world_inline_script_parsing():
    # 인라인 <script> 텍스트 파싱(격리월드 대응) — 라이브 전역이 아니라 스크립트 텍스트에서 상태 추출
    assert "_scriptStates" in EX
    assert "script:not([src])" in EX                      # 인라인 스크립트 텍스트 스캔
    assert "_sliceBalanced" in EX                          # 균형 매칭 JSON 조각 절단
    assert "격리 월드" in EX or "격리월드" in EX
    # live 전역 + 인라인 텍스트 둘 다 후보로
    assert "global[STATE_KEYS[i]]" in EX and "_scriptStates()" in EX


def test_walker_sku_image_rating_heuristics():
    assert "SKU_KEY" in EX and "res.skus.push" in EX       # sku 배열 → skus(스펙+가격)
    assert "_skuPriceSet" in EX                            # 메인 가격=첫 유효 sku
    assert "IMG_KEY" in EX and "pushImgs" in EX            # 이미지 배열(배열 키가 이미지류)→갤러리
    assert "RATE_KEY" in EX and "CNT_KEY" in EX            # 평점/리뷰수 키 휴리스틱
    assert "priceFromNum" in EX and "CENTS" in EX          # 숫자 가격 센트/소단위 환산


def test_states_variable_defined():
    # 회귀 가드: walker 루프의 states가 정의돼 있어야(초기 실수 재발 방지)
    assert "var states = _globalStates();" in EX
