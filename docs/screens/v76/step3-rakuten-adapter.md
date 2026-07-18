# v76 STEP3 — 라쿠텐(楽天市場) 상세 어댑터 신설

## 배경(오너 하네 기준선)
- 라쿠텐: 갤러리1. (실 스냅샷 미공급 — 합성 픽스처 `rakuten-detail.html`로 근본 재현·계약, 정직 표기.)

## 진단(근본)
라쿠텐 상세는 JSON-LD가 **가격 + 대표 1장**만 준다 → `needDom = !price || images.length===0`이 **false** →
제네릭 DOM 갤러리 수집 경로가 아예 안 돈다 → 갤러리가 og 1장에 그침(정확히 오너 하네 '갤러리1').

## 수리 — 라쿠텐 어댑터
- **`_rakutenGallery()`**: 호스트가 라쿠텐이면 DOM 갤러리를 **needDom과 무관하게 독립 수집·병합**(아마존식 독립 경로):
  - (a) 상세 본문 이미지(`item-detail`·`item_desc`·`sale_desc`) 먼저 별도 버킷 → URL 마킹.
  - (b) 갤러리 컨테이너(`image-gallery`·`ImageMain`·`ImageThumb`·`item-image`…) 스코프.
  - (c) 부족하면 **라쿠텐 CDN(`r10s.jp`·`image.rakuten.co.jp`·`thumbnail.image.rakuten.co.jp`) 이미지 전량**
    (추천/리뷰/상세 영역 `_galleryExcluded`·`_nonProdRegion`·`_inRakutenDetail`로 제외, 상세 버킷 URL 재중복 방지) → '전량' 보장.
- **`_ex=` 썸네일 파라미터 정규화**(`hiRes`): 라쿠텐 썸네일 `?_ex=128x128` 제거 → 원본 URL(썸네일↔원본 중복 제거).
- **3핵심 보장·정직 실패 표기**: 제목·가격·이미지는 표준 경로 + 어댑터로 확보. 필드별 `field_sources`(tier1/tier2/none)로
  어느 층이 줬는지 표기(가짜 소스 날조 0). 상세 본문 이미지는 `detail_images`/`desc_images`로 갤러리와 분리.

## 판정
- 가드 `tests/test_v76_rakuten_adapter.py`(3): manifest 핀 + source-contract(`_rakutenGallery`·`_RAKUTEN_CDN`·
  `_inRakutenDetail`·병합 배선·`_ex` 정규화) + **Playwright 실 kgp-extractor**: 갤러리 6장(≥5·`rec-*` 제외·`_ex` 제거·
  대표=`item-main`) + 상세 이미지 분리(`desc-1/2`, 갤러리 미혼입) + 3핵심(제목 折りたたみ椅子·3980 JPY·이미지) + 제목 사이트명 0.
- 실페이지 하네스 신규 픽스처 `rakuten-detail`(`images_min:5`·`images_max:6`·`images_exclude_substr:[rec-*]`·
  `title_excludes:[楽天市場·楽天·rakuten]`) → 실 추출로 계약 검증(하네스 7픽스처).
- **판정 캡처**: `step3-rakuten-adapter.png`(BEFORE 갤러리 1장 → AFTER 갤러리 6장 전량·대표=상품·`_ex` 제거 +
  상세 분리(desc-1/2) + 추천(rec) 제외).
- manifest 1.5.99→**1.5.100**(재로딩) + 버전핀.

## 같은 유형 버그 동반 수정(정직)
- 3자리 패치(1.5.100) 진입으로 `test_v55_tier1_sanity`·`test_v56_temu_verdict`의 **문자열 버전 비교**(`>= "1.5.56"`)가
  `"1.5.100" < "1.5.56"`로 오판 → **숫자 semver 튜플 비교**로 수리(latent 버그, 이번에 함께 잡음).

## 정직 표기(한계)
- 실 라쿠텐 스냅샷 미공급 → 합성 구조 픽스처로 계약. 오너 실기기 라쿠텐 1건 드로어 5탭 검증은 오너 몫.
- 실패 필드(예: 옵션 없는 상품)는 `none`/빈 채 유지 — 가짜 값 0.

## 금지 준수
- 가짜 성공 0(추천/리뷰 이미지 갤러리 혼입 제외·없는 갤러리 생성 안 함) · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
