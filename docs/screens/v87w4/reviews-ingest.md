# v87-W4 — 리뷰·평점 수신·저장·표시 갭 수리

## 오너 확정 사실 (재조사 금지)
확장(1.5.144, 77059d9)이 payload_echo `reviews_n=10 · rating 4.7 · review_count 22` **송신 확정**.
서버 레코드는 '부분 수집 — 리뷰·평점 누락(4/5)'. **확장 무죄** — 이 트랙은 서버 수신·저장·표시만 본다.
확장 디렉토리 불가침.

## ① 근원 특정 (근거 1줄)
> `src/api/extension_api.py` 재수집(force) 덮어쓰기 병합 `_merged.update({...})`이
> **reviews/rating/review_count 키를 포함하지 않아**, 새 수집이 리뷰 10·평점 4.7을 보내도 `_merged`엔
> 최초수집(리뷰 없음)의 빈 값이 남고, 그 `_merged`로 `compute_collect_status`를 재계산 → **4/5 고정**.

실증(로컬): 최초수집(리뷰 0) → 재수집(force, reviews=10/rating=4.7/review_count=22) 후 저장 레코드
`collect_status=부분 4/5 missing=['리뷰·평점'] · extra reviews_n=0 rating='' review_count=''`.
(신규 수집 경로는 reviews/rating/review_count를 이미 저장 — 결함은 **재수집 병합만**. 오너 행은 08-12
최초수집 후 1.5.144 재수집이라 이 경로를 탔다.)

## ② 수리 (서버만 — 확장 불가침)
- **저장 배선**(`extension_api.py`): force 병합에 `reviews/rating/review_count/detail_specs` 추가.
  정직 규칙 **new-if-nonempty**: 새 수집이 값을 주면 갱신, 안 주면 기존 보존(재수집 누락으로 기존 리뷰
  삭제 금지 = 비파괴). `recollected_at`(최근 갱신 시각)도 기록(참고 칩: 최초/최근 분리).
- **드로어 표시**(`collect_preview.html` 상세페이지 탭): `리뷰 N건 · 평점 X/5`. 빈 값이면
  **'리뷰 0건 수신 — 이 상품 페이지에서 리뷰·평점을 찾지 못했어요'**(조용한 미렌더 금지).
- **목록 표시**(`collect_history_rows.html` + `views.py`): 행에 `리뷰 N · X/5` 컴팩트 노출.
- **PG 프로젝션**(`collect_history_pg.py` `_LEAN_EXTRA`): 목록 lean 쿼리에 `rating`/`review_count`/
  `recollected_at` 스칼라 추가(대형 reviews 배열은 안 끔 — 속도 유지). **스키마 변경 0**(jsonb 프로젝션만).
- **5필드 판정**: reviews present → `리뷰·평점` filled → **5/5 성공**(판정기는 이미 리뷰 카운트, 병합
  누락만이 원인이었음).

## ③ 정직 — 빈 리뷰
`리뷰 0건 수신`으로 명시. 조용한 미렌더 금지(기존 원칙).

## 완료 보고 조건 (5항 + 해시)
1. **계약 그린 + 인위회귀**: `tests/test_v87_w4_reviews_ingest.py`(9) — 판정기 리뷰 반영/누락 정직,
   E2E 재수집 5/5·비파괴·신규수집 5/5, **인위회귀**(병합 리뷰 키 제외→4/5 red / 포함→5/5 green), 표시(드로어·
   목록·PG 프로젝션). ✅
2. **배포 해시 + /health**: 머지 후 해시. `/health` 200(storage 신호 유지 — W3). (W4는 /health 신설 없음.)
3. **운영 실증(최종 판정)**: 오너가 기존 08-12 행에서 **[다시 수집] 1회** → 드로어에 `리뷰 22건 · 평점 4.7`,
   상태 배지 **5/5 성공** 확인.
4. **참고 칩**: 최초수집(`collected_at`)/최근갱신(`recollected_at`) 분리 — 재수집 시각 옛값 고정 해소.

## 금지 구조 준수
- **확장 디렉토리 무변경**(서버 수신·저장·표시만 수리).
- **Supabase 스키마 ADD만 · DROP 금지**: 스키마 변경 0(jsonb 프로젝션 필드 추가만).
- **실유저 데이터 무손대**: 자동 이관·삭제 없음. 기존 행은 오너의 [다시 수집]으로만 갱신(비파괴).

## 캡처
`reviews-ingest-before-after.png` — BEFORE(재수집 4/5·reviews_n=0) / AFTER(5/5·reviews_n=10·평점 4.7·
드로어·목록 표시) + 비파괴·인위회귀.
