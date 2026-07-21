# v79 STEP4 — 갤러리 오염 필터

## 증상(오너 실기기 1.5.108)
- **테무**: kwcdn 중 배너·쿠폰(`material-put`·`upload_aimg`·`aimg`) 꼬리 8장이 갤러리에 혼입.
- **라쿠텐**: 타상품 추천·리뷰 별점 gif·배너 혼입.
- **알리**: `80x80`·`640x640` 썸네일 변형이 원본과 별개로 중복.

## 수리
1. **`_galleryScopeHost(list)`**(신설, host별) — 갤러리 조립 후 적용.
   - **테무**(`temu.com`): kwcdn 이미지는 `/product/` 경로만 허용, `material-put`·`marketing`·`upload_aimg`·`aimg` 배너/쿠폰 제외. 비-kwcdn은 유지.
   - **라쿠텐**(`rakuten.*`): 현재 shop 슬러그(`/<shop>/`)를 URL에서 도출 → r10s/image.rakuten CDN 이미지가 그 슬러그를 안 가지면(타 shop 추천) 제외. 비-라쿠텐 CDN은 유지.
   - 비대상 호스트·비-CDN 이미지는 **무영향**.
2. **`hiRes` 알리 썸네일 변형 정규화** — `.jpg_80x80xz.jpg`·`.jpg_640x640q90.jpg` → 원본 `.jpg`로 정규화 → `uniqPush` dedupe로 변형 중복 소멸.

## 계약(브리프)
> STEP 4 — 갤러리 내 배너·타상품 0.

## 판정
- 가드 `tests/test_v79_gallery_filter.py`(6): source-contract + **node 단위**(`_galleryScopeHost`: 테무 kwcdn 배너 제외·상품 경로만 / 라쿠텐 타 shop 제외 / 비대상 호스트 무영향) + **Playwright**: 알리 `80x80`·`640x640` 변형 + 원본 → 원본 2장만(변형 접미 0·중복 0).
- 기존 이미지 하네스(테무·라쿠텐·아마존·알리 갤러리/상세) 전량 그린(회귀 0).
- **판정 캡처**: `step4-gallery-filter.png`(3마켓 BEFORE/AFTER).
- 전체 **11455 passed / 22 skipped**. manifest 1.5.111→**1.5.112**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 실상품 이미지 소실 0(테무 `/product/`·라쿠텐 현재 shop·비-CDN 유지) · 배너/타상품은 정직 제외.

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
