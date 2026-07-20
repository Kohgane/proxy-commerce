# v78 STEP2 — 리뷰 메타 수리

## 근거(오너 실기기 진단 로그, ext 1.5.102)
- 테무: `reviews: 8, rating: "1", review_count: "0"` — 더미 평점 + 스테일 카운트.
- 아마존: `reviews: 9, rating: 없음` — 평점 미매핑.

## 근본 원인
- **더미 rating "1"**: `RATE_KEY`(`score` 등 광범위)가 상태 JSON의 비-평점 필드(`score:1` 등 관련도 점수)를 평점으로
  오채택. 채택 조건이 `rn > 0`이라 더미 0·1도 통과.
- **스테일 review_count "0"**: `CNT_KEY`가 초기 상태의 스테일 `review_count:0`을 그대로 채택(실 리뷰 8건과 불일치).

## 수리 — 리뷰 메타 정직화
- **상태 워크 rating 관문**: `rn > 1 && rn <= 5`만 채택(더미 0·1 skip → 뒤의 실 평점이 이기게).
- **최종 정직화**(오케스트레이션): rating이 `(1,5]` 아니면 **없음**(빈값). review_count는 `max(추출값, reviews.length)` —
  **실 추출 리뷰 수 이상**(스테일 0/불일치 보정). 확인 안 되면 없음(가짜 평점/카운트 저장 0).

## 계약(브리프)
> STEP 2 — reviews>0이면 rating 1.0~5.0 또는 없음(0·1 더미 금지), review_count ≥ reviews.

## 판정
- 가드 `tests/test_v78_review_meta.py`(4): source-contract(상태 워크 `rn>1` 관문·최종 rating 정직화·count 바닥 보정) +
  **Playwright**: 테무 더미(`score:1`·`review_count:0`·리뷰 8) → rating 더미 아님(1<r≤5)·review_count≥8 / 아마존 →
  rating 없음 or (1,5]·count≥리뷰수.
- 실페이지 하네스에 `rating_no_dummy`·`review_count_gte_reviews` 계약 키 추가 + 신규 픽스처 `temu-review-dummy`.
- **판정 캡처**: `step2-review-meta.png`(테무 rating "1"→실평점·count "0"→8 / 아마존 rating 없음(정직)).
- manifest 1.5.105→**1.5.106**(재로딩) + 버전핀.

## 정직 표기
- 실기기 진단 파일 미첨부 → 오매핑 구조를 합성 픽스처로 재현(오너 로그 reviews:8·rating:"1"·review_count:"0" 근거).
- 평점 확인 불가 시 "없음"(빈값) — 가짜 평점 생성 0. 진짜 aggregateRating이 있으면 우선 채택(JSON-LD).

## 금지 준수
- 가짜성공/더미 저장 0(0·1 rating·스테일 count 거부) · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
