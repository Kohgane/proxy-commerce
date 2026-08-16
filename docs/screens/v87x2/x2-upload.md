# v87-X2 · 업로드 화면(마켓 등록 모달) 에디토리얼 격상

STEP3 화면 순회 2/3. `collect_preview.html`의 마켓 등록 모달(Step1 마켓 선택 → 사전검증 → 결과).
gogabridj-design 토큰으로 부트스트랩 색 잔재 제거(기능·정보구조 불변).

## 변경(BEFORE → AFTER)
- 사전검증 뱃지: `badge bg-success`(통과, 채움 초록)·`badge bg-danger`(실패, 채움 적) → `pc-badge pc-badge-on`(청록)·`pc-badge pc-badge-danger`(적) — 은은한 토큰 필.
- 상태 안내: `alert alert-warning`(통과 마켓 없음)·`alert alert-info`(업로드 대상 요약)·`alert alert-danger`(오류) → `pc-status pc-status-warning/info/danger`.
- 강조: `text-primary`(파랑) — 목표 마진율 %·환율 프리뷰·스피너 → `text-teal`(청록).
- 헤더 뱃지: `badge bg-info text-dark`(수정됨)·`badge bg-warning text-dark`(목업)·`badge bg-secondary`(관리자) → `pc-badge` 변형.
- 가격 경고: `alert alert-warning`(priceWarn) → `pc-status pc-status-warning`.

## 정직·불변
- `btn-primary`/`btn-success`는 app.css에서 이미 청록/토큰 매핑 → 그대로 유지(다운그레이드 아님).
- 결과 상세(등록됨/큐/실패) 마켓별 뱃지는 v44-1의 토큰 color-mix 유지. 기능 0 제거.

캡처: `x2-upload.png`(좌 BEFORE / 우 AFTER, 모달 실호출 렌더 — 사전검증 결과 포함).
