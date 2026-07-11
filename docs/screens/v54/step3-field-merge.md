# v54 STEP3 — 잔여 정합

## ① 필드 병합 우선순위 명문화: tier1 > ld+json > tier2 DOM > og
- **tier1** = 확장이 클릭시점 API 캡처(자가진단 채택 포함)/DOM에서 읽어 **payload에 이미 담아 보낸 값**.
- 서버 보강(`_merge_*`)은 **빈 필드만** 채우므로 payload(tier1) 값이 항상 우선. 그 다음 **ld+json**(서버 1차),
  그 다음 **UniversalScraper**(DOM=tier2 → og=tier3).
- **출처 라벨도 동일 순서**: `compute_collect_status(sources={**_srv_src(ldjson), **client_field_sources(tier1/tier2)})`
  → 클라(tier1/tier2)가 서버(ldjson)를 덮는다. extension_api에 규약 주석 명문화.
- 실증: tier1 payload price=20605 + html ld+json price=55000 → **저장 20605**·라벨 Tier1. tier1 없으면 ld+json(55000).

## ② 상태 배지 5필드 카운트 (7/7 표기 오류 정리)
- FIELDS를 7→**5(드로어 5탭 기준)**: 가격·갤러리·옵션·상세·리뷰. **제목은 카운트 제외**(거의 항상 있음 →
  '7/7' 인플레 제거), fields엔 `count:false`로 표시(소스 로그용).
- **'상세'** = 상세설명(≥20자) **또는 상세이미지 배열**(테무 상세 본체) present.
- core={가격,갤러리}: 하나 누락=부분, 둘 다 누락=실패(정직). 배지 `성공 N/5`.

## 판정 (오너)
수집 이력 상태 배지가 **N/5**로 표기 + 부분 시 누락 필드명(가격·갤러리·옵션·상세·리뷰) 캡처.

## 가드
test_v54_field_merge(5): 5필드 카운트·상세(desc∨detail_images)·우선순위 주석·tier1>ldjson E2E·ldjson 폴백.
+ v47/v49 status 테스트 5필드/2-core 반영.
