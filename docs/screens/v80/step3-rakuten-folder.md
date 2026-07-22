# v80 STEP3 — 라쿠텐 갤러리 타상품 (마감 1)

## 증상(오너 실기기 1.5.114)
라쿠텐 갤러리에 추천 타상품 10장 혼입.

## 근본 원인
v79 STEP4의 `_galleryScopeHost` 라쿠텐 필터는 **shop 슬러그** 레벨 — `/mystore/`가 URL에 있으면 통과.
그런데 **같은 shop의** 타상품 추천은 같은 슬러그(`/mystore/`)를 갖고 다른 **상품 폴더**(`/cabinet/other/`)에
있어 필터를 통과 → 갤러리 leak. 또한 `_rakutenGallery`의 (c) CDN 스윕이 bare `<img>` 추천을 잡던 경로.

## 수리 — 현 상품 폴더 스코프 (di 동형)
- **`_rakutenFolder(u)`**(신설): 이미지 URL의 **디렉토리**(쿼리/해시 제거 후 마지막 `/` 이후 절삭).
- `_rakutenGallery` (b) 컨테이너 이미지(현 상품, 신뢰) + **og:image**(대표)의 디렉토리를 **유효 폴더셋**으로 도출.
- (c) CDN 스윕에서 **폴더셋 밖**(같은 shop 타상품 folder)을 제외 → 갤러리 타상품 0. 폴더셋이 비면 스코프
  미적용(v79 STEP4 shop-slug 필터가 교차-shop만 커버 — 무회귀).

## 계약(브리프)
> STEP 3 — di의 현 상품 폴더 스코프 로직을 갤러리에도 적용. 계약: 라쿠텐 픽스처 갤러리 타상품 0.

## 판정
- 가드 `tests/test_v80_rakuten_gallery_folder.py`(3): source-contract(`_rakutenFolder`·폴더셋 스코프·og:image 시드) +
  **Playwright**: 라쿠텐 상세(갤러리=현 상품 `/cabinet/roller/` 2장 + 같은 shop 추천 `/cabinet/other/` 3장 bare img) →
  갤러리에 **타상품 폴더(`/cabinet/other/`) 0**, 현 상품 폴더(`roller`) 이미지 유지.
- 기존 라쿠텐/갤러리 하네스(`test_v76_rakuten_adapter`·`test_v79_gallery_filter`·실페이지) 그린(회귀 0).
- **판정 캡처**: `step3-rakuten-folder.png`(BEFORE shop-slug 통과 → AFTER 폴더 스코프 제외).
- 전체 **11472 passed / 22 skipped**. manifest 1.5.116→**1.5.117**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 현 상품 이미지 소실 0 · 타상품은 정직 제외.

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
