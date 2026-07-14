# v70 STEP3 — 갤러리 스코프 (현행범 버그③)

## 증상 (오너 실측)
- 이미지 58장 — 갤러리 스코프 실패(관련상품·스프라이트·1px 혼입).
- 근원: 브로드 제네릭 갤러리 셀렉터(`[class*="thumb" i] img`·`[class*="carousel" i] img` 등)가 아마존에서 관련상품 캐러셀·스프라이트까지 흡수.

## 수리 (`kgg-extractor.js` `_domImages`)
1. **아마존 전용 스코프 분기**: host가 amazon이면 `_amazonGallery()`로 **`#altImages`(썸네일 스트립) + `#imgTagWrapper(Id)`(메인) + `#landingImage`·`#imageBlock`·`#ivLargeImage`·`#main-image-container`만** 스캔 → 브로드 제네릭 갤러리(58장 근원) **early-return으로 건너뜀**.
2. **고해상 승격**: `_amazonDynMax(im)` = `data-a-dynamic-image`(url→[w,h] JSON)에서 최대 면적 URL 선택. `_bestImgSrc`가 `data-old-hires`/`data-zoom` 우선. `hiRes()`가 `._AC_SL500_`·`._SS40_` 크기 토큰 제거로 원본 해상도화.
3. **배제**: 스프라이트·1px(naturalWidth/height < 40 + `NONPROD_IMG`(sprite/icon/pixel)) 제외. 관련상품은 스코프 밖이라 자연 배제.
4. **상세(별도 버킷)**: `#aplus`·`#productDescription`·`#feature-bullets`·`#aplus_feature_div` 이미지는 detailImages로.
- 비아마존은 기존 제네릭 갤러리 스코프 유지(회귀 0).

## 판정
- 가드 `tests/test_v70_gallery_scope.py` (3):
  - 소스계약(_amazonGallery·_amazonDynMax·altImages/imgTagWrapper 스코프·dynamic-image·early-return).
  - **node 실증**: 스코프(메인+썸네일4+스프라이트) + 관련상품 53장 브로드 셀렉터 → `_amazonGallery`는 **자기 상품 5장만**(관련상품 REL 혼입 0·스프라이트 0·SL1500 hi-res 승격, SL500/SS40 크기토큰 제거).
  - manifest 1.5.78.
- 회귀: `test_v57_temu_images`·`test_v57_generic_images`·`test_v44_img_detail_extract` 그린(비아마존 경로 불변).
- **실기기(오너 몫)**: 아마존 상세 → 드로어 썸네일 탭 = 자기 상품 5~15장 캡처 + F12 갤러리 수 감소 로그. (개발 프록시 라이브 아마존 차단.)

## 금지 준수
- 무스코프 갤러리 0(아마존 스코프 한정) · 스프라이트/1px/관련상품 혼입 0 · 서버측 직접 크롤 0(확장 DOM).

적용 스킬: (확장 추출 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
