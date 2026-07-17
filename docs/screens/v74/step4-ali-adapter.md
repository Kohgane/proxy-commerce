# v74 STEP4 — 알리 상세 어댑터 완성 + 숫자 정규화 공통 유틸

## 증상
알리 상세: 가격 **"6620."**(후행 점)·갤러리 **3장 과소**·**옵션 0**(sources: options=none).

## 근본
1. `STATE_KEYS`에 알리 초기상태 키 **`runParams`** 없음 → `window.runParams.data.{imageModule, skuModule}` 미파싱
   → 갤러리는 DOM 폴백뿐(과소), 옵션 미추출.
2. sku 값 키 `propertyValueDisplayName`가 `_OPT_VAL_KEY` 미매치 + 중첩 값이 부모 축명(`skuPropertyName`)을 못 물려
   받음 → **옵션 0**.
3. 후행 점 정규화 부재 → 마켓이 "6620." 거부.

## 수리 (추출기 동결 예외 — 알리 어댑터·숫자 정규화, 하네스 계약 동반)
- **`runParams` STATE_KEY 추가** → 알리 JSON(imagePathList·productSKUPropertyList) 파싱.
- **숫자 정규화 공통 유틸 `_normNum`**(전 어댑터): 천단위·공백·통화기호·**후행 점** 제거 → 항상 `\d+(\.\d+)?`.
  최종 `price = _normNum(price)`(sanity 이전) 단일 관문.
- **`_OPT_VAL_KEY` 확장**(`propertyvalue|valuedisplayname`) + **중첩 값에 부모 축명 상속**(자식=값만일 때
  '옵션' 뭉뚱그림 대신 Color/Size 귀속).
- 갤러리는 imagePathList로 전량, 옵션은 sku 축별([옵션명·값·값이미지], 테무 v71 스키마 동형). 상세/리뷰는 JSON
  내 존재분 우선 + 없으면 기존 보강 창 경로(정직 표기 유지).

## 판정 (하네스 그린)
- 가드 `tests/test_v74_ali_adapter.py`(4): source-contract(runParams·_normNum·_OPT_VAL_KEY·부모축) +
  **node 정규화 계약**(6,620.→6620·₩6,620.→6620·1 234→1234·빈/비숫자→''·전부 `^\d+(\.\d+)?$`) +
  **Playwright 실 kgp-extractor**(알리 픽스처 → price=6620·KRW·img≥6·options≥1·Color 값·priceMatchesContract).
- 실페이지 하네스 `tests/test_v70_realpage_harness.py`에 **ali-detail 편입**(계약 스냅샷). 기존 temu/amazon 그린(회귀 0).
- **판정 캡처**: `step4-ali-detail-extraction.png`(추출 결과 카드: price 6620 KRW·갤러리 10·옵션 Color/Ships From·tier1).
- 픽스처 `fixtures/realpages/ali-detail.html`+`.expected.json`(오너 실스냅샷 공급 시 교체).
- manifest 1.5.95→**1.5.96**(재로딩) + 버전핀.
- **실기기(오너 몫)**: 알리 상세 1건 수집 → 드로어 5탭(상품명·가격·옵션·썸네일·상세) 캡처(확장 1.5.96 재로딩 후).

## 금지 준수
추출기 무계약 변경 0(알리·정규화만, 하네스 동반) · 가짜 성공 0(실 추출기·실 픽스처) · temu/amazon 회귀 0.

적용 스킬: (추출기 어댑터 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
