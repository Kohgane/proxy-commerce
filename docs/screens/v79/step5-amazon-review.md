# v79 STEP5 — 아마존 리뷰 본문·평점

## 증상(오너 실기기 1.5.108)
- 아마존 리뷰 `text` = `author` **복제**(본문 셀렉터가 저자 노드를 잡음).
- 리뷰 `rating` 미매핑(없음).

## 근본 원인
`_domReviews`의 본문 셀렉터가 넓은 `[class*="content" i]`·`p`를 포함 → `querySelector`는 **문서 순서
first-match**를 반환하는데, 아마존 리뷰 카드는 저자 프로필(`.a-profile-content`)이 본문보다 **앞**에 있어
`bodyEl`이 저자 노드로 해석됨 → `text === author` 복제.

## 수리
- **본문 셀렉터를 구체적 리뷰 본문만**으로: `[data-hook="review-body"]`·`[itemprop="reviewBody"]`·
  `[class*="review-text"]`·`[class*="review-content"]`·`[class*="comment-text"]` **순차** 시도.
  넓은 `[class*="content"]`·`p` 폴백(저자 복제 근원) **제거**.
- **저자 노드 배제**: 후보가 `closest(AUTH_SEL)`(`.a-profile-*`·author·reviewer…) 하위면 스킵.
- **`text≠author` 봉인**: 후보 텍스트가 저자명과 같으면 채택 안 함. 본문을 못 찾으면 **스킵**(저자 복제 저장 금지).
- **rating 매핑**: `X out of 5 stars`(`.a-icon-alt`) → `X`(원본 형식 `5.0` 보존), 없으면 class(`a-star-4`·
  `rating-4`) 폴백. **1.0~5.0만** 채택(더미·범위 밖 배제).

## 계약(브리프)
> STEP 5 — text≠author, rating 1.0~5.0.

## 판정
- 가드 `tests/test_v79_amazon_review.py`(3): source-contract + **Playwright**(아마존 리뷰 카드 3건, 저자 노드가
  본문보다 DOM 앞) → 전 리뷰 `text≠author`·본문 실제 내용·rating `5.0`/`4.0`/`3`(class 폴백).
- 기존 `test_v76_amazon_reviews` 그린(원본 형식 `5.0` 보존 — 회귀 0).
- **판정 캡처**: `step5-amazon-review.png`(BEFORE text=author 복제 → AFTER 본문·평점 정상).
- 전체 **11458 passed / 22 skipped**. manifest 1.5.112→**1.5.113**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 저자 복제 저장 0(정직 — 본문 없으면 스킵) · 가짜 평점 0(1~5만).

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
