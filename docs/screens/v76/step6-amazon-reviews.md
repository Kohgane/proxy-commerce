# v76 STEP6 — 아마존 리뷰 (DOM 폴백, 존재분만)

## 배경(오너 하네 기준선)
- 아마존 리뷰: 초기 JSON-LD/state에 리뷰가 없으면 리뷰 0. 상세 리뷰 섹션 상위 텍스트 수집(추가 요청 금지, 페이지 내 존재분만).

## 진단
기존 리뷰 추출은 **JSON-LD Product.review + state review 노드**(`_fromJson`)에서만 읽었다. 아마존은 리뷰가
JSON-LD에 없고 DOM(`#cm-cr-dp-review-list`·`[data-hook="review"]`)에만 렌더 → 리뷰 0.

## 수리 — DOM 리뷰 폴백
- **`_domReviews()`**: 페이지에 **이미 렌더된** 리뷰 항목(`[data-hook="review"]`·`[itemprop="review"]`·`[class*="review-item"]`…)의
  상위 텍스트를 읽는다 — 본문(`[data-hook="review-body"]`·`[itemprop="reviewBody"]`·review-text)·평점(`a-icon-alt` "5.0 out of 5"→5.0,
  1..5 검증)·작성자(`a-profile-name`·author). **추가 네트워크 요청 0**(DOM만 읽음, fetch/XHR 미사용) — '존재분만'.
- **독립 병합**: 초기 JSON 리뷰가 부족(<3)할 때만 `_domReviews` 병합, **본문 40자 중복 제거**(JSON+DOM 이중 카운트 방지).
- **정직 소스 표기**: DOM 리뷰는 `field_sources.reviews = "tier2"`(JSON=tier1, 없으면 none — 가짜 소스 날조 0).

## 판정
- 가드 `tests/test_v76_amazon_reviews.py`(4): manifest 핀 + source-contract(`_domReviews`·`[data-hook=review]`·독립 병합·
  **추가요청 0**(fetch/XHR 미사용)·tier2 표기) + **Playwright 실 kgp-extractor**: 아마존 리뷰 3건(본문·평점 5.0·작성자·
  '충전' 텍스트) + tier2 + 갤러리/상세 회귀 0 + **리뷰 섹션 없는 테무·알리·라쿠텐 오검출 0**(추천/설명을 리뷰로 오인 금지).
- 실페이지 하네스에 `reviews_min`/`reviews_contains` 계약 추가 → 아마존 픽스처 `reviews_min:3`·`reviews_contains:충전`.
- **판정 캡처**: `step6-amazon-reviews.png`(BEFORE JSON 리뷰 0 → AFTER DOM 리뷰 3건 tier2·본문·평점·작성자).
- manifest 1.5.101→**1.5.102**(재로딩) + 버전핀.

## 정직 표기(한계)
- 실 아마존 스냅샷 미공급 → 합성 구조 픽스처(`#cm-cr-dp-review-list`)로 계약. '추가 요청 금지'(더보기 페이지 크롤 안 함) 준수 —
  현재 페이지에 렌더된 리뷰만. 리뷰 섹션 없는 상품은 0(정직).

## 금지 준수
- 가짜 성공 0(존재분만·빈 리뷰 금지) · 추가 네트워크 요청 0 · 오검출 0(비-리뷰 페이지 0) · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
