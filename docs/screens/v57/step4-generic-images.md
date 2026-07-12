# v57 STEP4 — 제네릭 이미지 보강

## 서버 union (extension_api.py)
- 신규 `_union_images(*sources)` — 여러 이미지 소스를 **순서 보존 union + 중복 제거** → filter_product_images.
  클라(tier1/DOM)가 앞, 그 뒤로 미포함분만 append. 로고/아이콘은 필터 제거.
- 신규 `_og_images_from_html(html)` — og:image / og:image:url / og:image:secure_url 다중 태그(순서 보존).
- 수집 파이프라인: ld+json image 배열(`_ld_images`) 캡처 + og:image 추출 →
  `_union_images(클라 gallery, 클라 images, ld+json, og)` → payload images/gallery_images 갱신.
  기존 `_merge`(빈 필드만 채움)와 달리 **이미 이미지가 있어도 누락분을 뒤에 append** → 제네릭 갤러리 누락 0.

판정: 순서보존·중복0·og 다중·로고필터 union(test_union_*), 파이프라인 배선.

## 클라 셀렉터 확장 (kgp-extractor.js `_domImages`/`_bestImgSrc`)
- **롤오버/줌 data-***: `_bestImgSrc`가 data-zoom-image·data-large·data-large-image·data-image-large·
  data-hires·data-old-hires·data-zoom 우선(고해상), 그 다음 currentSrc/data-src… srcset/data-srcset 최대.
- **picture > source**: 갤러리 스코프의 `picture source[srcset]` 최대 해상도 후보 수집.
- **인라인 background-image**: `_bgImage(el)`가 `style="background-image:url(...)"` URL 추출 →
  div/a 기반 갤러리(img 태그 없는) 대응.

판정: test_v57_generic_images(7, node 실행 — 줌 data-* 우선·background-image URL 추출). 관련 46 pass.
